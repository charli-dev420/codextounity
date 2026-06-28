using System;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace AIAssetFactory.EditorTools
{
    public static class AIAssetPipelineCommands
    {
        private const string PromptFileSuffix = "_reference_prompt.txt";
        private const string ReferenceFileSuffix = "_reference";

        [MenuItem(AIAssetConstants.MenuRoot + "/Create Request From Selected Prefab")]
        public static void CreateRequestFromSelectedPrefab()
        {
            var selectedObject = Selection.activeObject;
            if (selectedObject == null)
            {
                Debug.LogError("[AIAssetFactory] No selection.");
                return;
            }

            var prefabPath = AssetDatabase.GetAssetPath(selectedObject);
            var sourceObject = TryGetGameObjectFromSelection(selectedObject, prefabPath);
            if (sourceObject == null)
            {
                Debug.LogError("[AIAssetFactory] Selection is not a prefab root/gameobject.");
                return;
            }

            var sourceName = sourceObject.name;
            var request = new AIAssetRequest
            {
                requestId = $"REQ_{SanitizeId(sourceName)}_{DateTime.UtcNow:yyyyMMdd_HHmmss}",
                assetId = $"AI_{SanitizeId(sourceName)}_{DateTime.UtcNow:yyyyMMdd_HHmmss}",
                sourcePrefabId = sourceName,
                sourcePrefabPath = string.IsNullOrWhiteSpace(prefabPath) ? string.Empty : prefabPath.Replace('\\', '/'),
                category = GuessCategory(sourceName),
                zoneId = string.Empty,
                zoneTheme = "project-defined",
                targetSizeMeters = GuessTargetSizeMeters(sourceObject),
                status = AIAssetStatus.DraftRequest,
                validationProfile = "CodexPostGeneration",
                comfyWorkflow = "trellis2_low-poly.ui.json"
            };
            request.referenceImages = Array.Empty<string>();
            request.Write();

            Debug.Log($"[AIAssetFactory] Request created: {request.requestId}");
            EditorUtility.RevealInFinder(AIAssetRequest.GetRequestPath(request.requestId));
        }

        [MenuItem(AIAssetConstants.MenuRoot + "/Build Reference Prompt From Request")]
        public static void BuildReferencePromptFromRequest()
        {
            var request = LoadSelectedRequest("Select request to build a reference prompt");
            if (request == null) return;

            var prompt = BuildPrompt(request);
            Directory.CreateDirectory(AIAssetConstants.RequestsFolder);
            request.imagenPromptPath = $"{AIAssetConstants.RequestsFolder}/{request.requestId}{PromptFileSuffix}";
            File.WriteAllText(request.imagenPromptPath, prompt);
            request.status = AIAssetStatus.AwaitingImagenReference;
            request.Write();
            EditorUtility.RevealInFinder(request.imagenPromptPath);

            Debug.Log($"[AIAssetFactory] Reference prompt saved -> {request.imagenPromptPath}");
            Debug.Log(prompt);
        }

        [MenuItem(AIAssetConstants.MenuRoot + "/Attach Reference Image")]
        public static void AttachReferenceImage()
        {
            var request = LoadSelectedRequest("Select request to attach a reference image");
            if (request == null) return;

            var picked = EditorUtility.OpenFilePanel("Pick reference image", AIAssetConstants.ReferenceFolder, "png,jpg,jpeg,webp");
            if (string.IsNullOrWhiteSpace(picked))
            {
                return;
            }

            if (!File.Exists(picked))
            {
                Debug.LogError($"[AIAssetFactory] Selected image not found: {picked}");
                return;
            }

            Directory.CreateDirectory(AIAssetConstants.ReferenceFolder);
            var extension = Path.GetExtension(picked);
            var dest = Path.Combine(AIAssetConstants.ReferenceFolder, $"{request.requestId}{ReferenceFileSuffix}{extension}");
            File.Copy(picked, dest, true);

            request.referenceImages = new[] { Path.GetFullPath(dest) };
            request.status = AIAssetStatus.ImagenReady;
            request.Write();

            Debug.Log($"[AIAssetFactory] Reference image attached to request {request.requestId}");
            EditorUtility.RevealInFinder(dest);
        }

        [MenuItem(AIAssetConstants.MenuRoot + "/Import Codex Result Manifest")]
        public static void ImportResultManifest()
        {
            var path = EditorUtility.OpenFilePanel("Import Codex result manifest", AIAssetConstants.ResultsFolder, "json");
            if (string.IsNullOrWhiteSpace(path))
            {
                return;
            }

            AIAssetResultImporter.ImportManifest(path);
        }

        [MenuItem(AIAssetConstants.MenuRoot + "/Open Requests")]
        public static void OpenRequestsFolder()
        {
            Directory.CreateDirectory(AIAssetConstants.RequestsFolder);
            EditorUtility.RevealInFinder(Path.GetFullPath(AIAssetConstants.RequestsFolder));
        }

        [MenuItem(AIAssetConstants.MenuRoot + "/Open Results")]
        public static void OpenResultsFolder()
        {
            Directory.CreateDirectory(AIAssetConstants.ResultsFolder);
            EditorUtility.RevealInFinder(Path.GetFullPath(AIAssetConstants.ResultsFolder));
        }

        [MenuItem(AIAssetConstants.MenuRoot + "/Open Generated Assets")]
        public static void OpenGeneratedFolder()
        {
            Directory.CreateDirectory(AIAssetConstants.GeneratedFolder);
            EditorUtility.RevealInFinder(Path.GetFullPath(AIAssetConstants.GeneratedFolder));
        }

        private static string BuildPrompt(AIAssetRequest request)
        {
            var sb = new StringBuilder();
            sb.AppendLine("Generate a single isolated 3D game asset reference image suitable for image-to-3D conversion.");
            sb.AppendLine();
            sb.AppendLine($"Asset type: {request.category}");
            sb.AppendLine($"Source prefab: {request.sourcePrefabId}");
            sb.AppendLine($"Target dimensions in meters: {request.targetSizeMeters}");
            sb.AppendLine($"Style: {request.visualStyle}");
            if (!string.IsNullOrWhiteSpace(request.zoneTheme))
            {
                sb.AppendLine($"Project theme: {request.zoneTheme}");
            }
            sb.AppendLine("Camera: orthographic 3/4 view, full object visible, centered, neutral background.");
            sb.AppendLine();
            sb.AppendLine("Constraints:");
            sb.AppendLine("- single object only");
            sb.AppendLine("- no text labels");
            sb.AppendLine("- no environment");
            sb.AppendLine("- preserve the broad source silhouette");
            sb.AppendLine("- preserve gameplay dimensions");
            sb.AppendLine("- clear readable silhouette");
            sb.AppendLine("- suitable for local ComfyUI image-to-3D conversion");
            sb.AppendLine();
            sb.AppendLine("Negative prompt:");
            sb.AppendLine("text, labels, logos, characters unless requested, clutter, realistic scene, cinematic background, tiny fragile details, multiple objects");
            return sb.ToString().Trim();
        }

        private static AIAssetRequest LoadSelectedRequest(string dialogTitle)
        {
            var selected = Selection.activeObject;
            string requestPath = null;
            if (selected != null)
            {
                var candidatePath = AssetDatabase.GetAssetPath(selected);
                if (!string.IsNullOrWhiteSpace(candidatePath) && candidatePath.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
                {
                    requestPath = candidatePath;
                }
            }

            if (string.IsNullOrWhiteSpace(requestPath))
            {
                requestPath = EditorUtility.OpenFilePanel(dialogTitle, AIAssetConstants.RequestsFolder, "json");
            }

            if (string.IsNullOrWhiteSpace(requestPath) || !File.Exists(requestPath))
            {
                Debug.LogError($"[AIAssetFactory] Request not found: {requestPath}");
                return null;
            }

            var requestJson = File.ReadAllText(requestPath);
            var request = JsonUtility.FromJson<AIAssetRequest>(requestJson);
            if (request == null)
            {
                Debug.LogError($"[AIAssetFactory] Invalid request JSON: {requestPath}");
                return null;
            }

            if (string.IsNullOrWhiteSpace(request.requestId))
            {
                request.requestId = Path.GetFileNameWithoutExtension(requestPath);
                request.Write();
            }
            return request;
        }

        private static GameObject TryGetGameObjectFromSelection(UnityEngine.Object selected, string assetPath)
        {
            if (selected is GameObject gameObject)
            {
                return gameObject;
            }

            if (!string.IsNullOrWhiteSpace(assetPath) && assetPath.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase))
            {
                return AssetDatabase.LoadAssetAtPath<GameObject>(assetPath);
            }

            return Selection.activeGameObject;
        }

        private static Vector3 GuessTargetSizeMeters(GameObject source)
        {
            var renderers = source.GetComponentsInChildren<Renderer>(true);
            if (renderers == null || renderers.Length == 0)
            {
                return Vector3.one;
            }

            var bounds = renderers[0].bounds;
            for (var i = 1; i < renderers.Length; i++)
            {
                bounds.Encapsulate(renderers[i].bounds);
            }

            return bounds.size;
        }

        private static string GuessCategory(string sourceName)
        {
            var lower = sourceName.ToLowerInvariant();
            if (lower.Contains("door")) return "Door";
            if (lower.Contains("terminal")) return "ObjectiveTerminal";
            if (lower.Contains("bridge") || lower.Contains("catwalk")) return "Bridge";
            return "Prop";
        }

        private static string SanitizeId(string input)
        {
            var safe = input.Replace(' ', '_');
            var chars = safe.ToCharArray();
            for (var i = 0; i < chars.Length; i++)
            {
                var c = chars[i];
                if (!char.IsLetterOrDigit(c) && c != '_' && c != '-')
                {
                    chars[i] = '_';
                }
            }
            return new string(chars).Trim('_');
        }
    }
}
