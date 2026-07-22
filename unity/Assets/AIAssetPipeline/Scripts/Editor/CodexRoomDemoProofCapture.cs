using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace AIAssetFactory.EditorTools
{
    public static class CodexRoomDemoProofCapture
    {
        public static void CaptureFromCommandLine()
        {
            var selectedReferences = GetCommandLineValue("-codexProofSelectedReferences");
            var manifestDir = GetCommandLineValue("-codexProofManifestDir");
            var scenePath = GetCommandLineValue("-codexProofScenePath");
            var importCapture = GetCommandLineValue("-codexProofImportCapture");
            var cleanCapture = GetCommandLineValue("-codexProofCleanSceneCapture");
            var reportPath = GetCommandLineValue("-codexProofReport");

            if (string.IsNullOrWhiteSpace(reportPath))
            {
                reportPath = Path.Combine(Application.dataPath, "../CodexRoomDemoProofCaptureReport.json");
            }

            var report = Capture(selectedReferences, manifestDir, scenePath, importCapture, cleanCapture);
            WriteReport(reportPath, report);
            if (!report.valid)
            {
                foreach (var error in report.errors)
                {
                    Debug.LogError($"[AIAssetFactory] Room demo proof capture: {error}");
                }
                EditorApplication.Exit(2);
                return;
            }

            Debug.Log("[AIAssetFactory] Room demo proof captures written.");
            EditorApplication.Exit(0);
        }

        private static ProofCaptureReport Capture(string selectedReferencesPath, string manifestDir, string scenePath, string importCapture, string cleanCapture)
        {
            var errors = new List<string>();
            var warnings = new List<string>();
            var assets = new List<ProofAssetReport>();

            if (string.IsNullOrWhiteSpace(selectedReferencesPath) || !File.Exists(selectedReferencesPath))
            {
                errors.Add($"selected_references.json not found: {selectedReferencesPath}");
                return BuildReport(importCapture, cleanCapture, assets, errors, warnings);
            }
            if (string.IsNullOrWhiteSpace(manifestDir) || !Directory.Exists(manifestDir))
            {
                errors.Add($"manifest directory not found: {manifestDir}");
                return BuildReport(importCapture, cleanCapture, assets, errors, warnings);
            }
            if (string.IsNullOrWhiteSpace(importCapture))
            {
                errors.Add("-codexProofImportCapture is required");
            }
            if (string.IsNullOrWhiteSpace(cleanCapture))
            {
                errors.Add("-codexProofCleanSceneCapture is required");
            }
            if (errors.Count > 0)
            {
                return BuildReport(importCapture, cleanCapture, assets, errors, warnings);
            }

            var references = LoadSelectedReferences(selectedReferencesPath, errors);
            if (references.Length == 0)
            {
                errors.Add("selected_references.json contains no assets");
                return BuildReport(importCapture, cleanCapture, assets, errors, warnings);
            }

            CaptureImportGrid(references, manifestDir, importCapture, assets, errors, warnings);
            CaptureCleanScene(scenePath, cleanCapture, errors, warnings);
            return BuildReport(importCapture, cleanCapture, assets, errors, warnings);
        }

        private static void CaptureImportGrid(SelectedReferencePayload[] references, string manifestDir, string capturePath, List<ProofAssetReport> assets, List<string> errors, List<string> warnings)
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            ConfigureLighting();
            var root = new GameObject("CodexRoomDemoProofImportGrid");
            var importedObjects = new List<GameObject>();
            var index = 0;

            foreach (var reference in references)
            {
                var assetReport = new ProofAssetReport
                {
                    assetName = reference.assetName,
                    profile = reference.profile,
                    role = reference.role,
                };
                assets.Add(assetReport);

                var manifestPath = FindManifest(manifestDir, reference.assetName);
                assetReport.manifestPath = manifestPath;
                if (string.IsNullOrWhiteSpace(manifestPath))
                {
                    var message = $"manifest not found for asset {reference.assetName}";
                    assetReport.errors = new[] { message };
                    errors.Add(message);
                    continue;
                }

                var imported = AIAssetResultImporter.ImportManifestForAutomation(manifestPath, false);
                if (!(imported is GameObject prefab))
                {
                    var importedType = imported == null ? "null" : imported.GetType().Name;
                    var message = $"imported asset is {importedType}, not a GameObject for {reference.assetName}";
                    assetReport.errors = new[] { message };
                    errors.Add(message);
                    continue;
                }

                var instance = PrefabUtility.InstantiatePrefab(prefab) as GameObject;
                if (instance == null)
                {
                    instance = UnityEngine.Object.Instantiate(prefab);
                }
                instance.name = reference.assetName;
                instance.transform.SetParent(root.transform, false);
                var column = index % 4;
                var row = index / 4;
                instance.transform.position = new Vector3(column * 2.4f, 0f, row * 2.4f);
                importedObjects.Add(instance);
                assetReport.imported = true;
                assetReport.sceneObjectPath = GetHierarchyPath(instance.transform);
                index++;
            }

            if (importedObjects.Count == 0)
            {
                errors.Add("no imported GameObject was available for import grid capture");
                return;
            }

            var camera = CreateCameraForBounds(CollectBounds(importedObjects), "CodexRoomDemoProof_ImportCamera");
            CaptureCamera(camera, capturePath);
        }

        private static void CaptureCleanScene(string scenePath, string capturePath, List<string> errors, List<string> warnings)
        {
            if (string.IsNullOrWhiteSpace(scenePath))
            {
                errors.Add("clean scene path is missing");
                return;
            }
            if (!File.Exists(scenePath))
            {
                errors.Add($"clean scene not found: {scenePath}");
                return;
            }

            var scene = EditorSceneManager.OpenScene(scenePath, OpenSceneMode.Single);
            if (!scene.IsValid())
            {
                errors.Add($"failed to open clean scene: {scenePath}");
                return;
            }

            var camera = Camera.main;
            if (camera == null)
            {
                var roots = scene.GetRootGameObjects();
                camera = CreateCameraForBounds(CollectBounds(roots), "CodexRoomDemoProof_CleanCamera");
                warnings.Add("clean scene had no MainCamera; proof capture created one");
            }
            CaptureCamera(camera, capturePath);
        }

        private static void ConfigureLighting()
        {
            RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Flat;
            RenderSettings.ambientLight = new Color(0.65f, 0.66f, 0.68f);
            var lightObject = new GameObject("CodexRoomDemoProof_KeyLight");
            var light = lightObject.AddComponent<Light>();
            light.type = LightType.Directional;
            light.intensity = 1.2f;
            lightObject.transform.rotation = Quaternion.Euler(50f, -35f, 0f);
        }

        private static Camera CreateCameraForBounds(Bounds bounds, string name)
        {
            var cameraObject = new GameObject(name);
            var camera = cameraObject.AddComponent<Camera>();
            camera.orthographic = true;
            var extent = Mathf.Max(bounds.extents.x, bounds.extents.y, bounds.extents.z, 1f);
            camera.orthographicSize = Mathf.Max(2.2f, extent * 1.35f);
            camera.nearClipPlane = 0.1f;
            camera.farClipPlane = 500f;
            var center = bounds.center;
            cameraObject.transform.position = center + new Vector3(5.2f, 4.0f, -6.0f);
            cameraObject.transform.rotation = Quaternion.Euler(35f, -42f, 0f);
            camera.backgroundColor = new Color(0.78f, 0.80f, 0.82f);
            camera.clearFlags = CameraClearFlags.SolidColor;
            return camera;
        }

        private static void CaptureCamera(Camera camera, string path)
        {
            var parent = Path.GetDirectoryName(path);
            if (!string.IsNullOrWhiteSpace(parent))
            {
                Directory.CreateDirectory(parent);
            }

            var renderTexture = new RenderTexture(1280, 720, 24, RenderTextureFormat.ARGB32);
            var previousTarget = camera.targetTexture;
            var previousActive = RenderTexture.active;
            try
            {
                camera.targetTexture = renderTexture;
                RenderTexture.active = renderTexture;
                camera.Render();
                var texture = new Texture2D(renderTexture.width, renderTexture.height, TextureFormat.RGB24, false);
                texture.ReadPixels(new Rect(0, 0, renderTexture.width, renderTexture.height), 0, 0);
                texture.Apply();
                File.WriteAllBytes(path, texture.EncodeToPNG());
                UnityEngine.Object.DestroyImmediate(texture);
            }
            finally
            {
                camera.targetTexture = previousTarget;
                RenderTexture.active = previousActive;
                renderTexture.Release();
                UnityEngine.Object.DestroyImmediate(renderTexture);
            }
        }

        private static Bounds CollectBounds(IEnumerable<GameObject> objects)
        {
            var initialized = false;
            var bounds = new Bounds(Vector3.zero, Vector3.one);
            foreach (var item in objects)
            {
                if (item == null) continue;
                foreach (var renderer in item.GetComponentsInChildren<Renderer>())
                {
                    if (!initialized)
                    {
                        bounds = renderer.bounds;
                        initialized = true;
                    }
                    else
                    {
                        bounds.Encapsulate(renderer.bounds);
                    }
                }
            }
            return initialized ? bounds : new Bounds(Vector3.zero, Vector3.one);
        }

        private static SelectedReferencePayload[] LoadSelectedReferences(string path, List<string> errors)
        {
            try
            {
                var json = File.ReadAllText(path);
                var trimmed = json.TrimStart('\uFEFF', ' ', '\r', '\n', '\t');
                if (!trimmed.StartsWith("[", StringComparison.Ordinal))
                {
                    var single = JsonUtility.FromJson<SelectedReferencePayload>(json);
                    return string.IsNullOrWhiteSpace(single?.assetName)
                        ? Array.Empty<SelectedReferencePayload>()
                        : new[] { single };
                }
                var wrapper = JsonUtility.FromJson<SelectedReferenceList>("{\"items\":" + trimmed + "}");
                return wrapper?.items ?? Array.Empty<SelectedReferencePayload>();
            }
            catch (Exception error)
            {
                errors.Add($"selected_references.json parse failed: {error.Message}");
                return Array.Empty<SelectedReferencePayload>();
            }
        }

        private static string FindManifest(string manifestDir, string assetName)
        {
            var safeName = SanitizeFileName(assetName);
            foreach (var candidate in new[]
            {
                Path.Combine(manifestDir, safeName + ".unity_manifest.json"),
                Path.Combine(manifestDir, assetName + ".unity_manifest.json"),
            })
            {
                if (File.Exists(candidate)) return candidate;
            }

            foreach (var candidate in Directory.GetFiles(manifestDir, "*.unity_manifest.json", SearchOption.AllDirectories))
            {
                var stem = Path.GetFileNameWithoutExtension(Path.GetFileNameWithoutExtension(candidate));
                if (string.Equals(stem, assetName, StringComparison.OrdinalIgnoreCase)
                    || string.Equals(stem, safeName, StringComparison.OrdinalIgnoreCase)
                    || stem.IndexOf(safeName, StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    return candidate;
                }
            }
            return string.Empty;
        }

        private static ProofCaptureReport BuildReport(string importCapture, string cleanCapture, List<ProofAssetReport> assets, List<string> errors, List<string> warnings)
        {
            return new ProofCaptureReport
            {
                schema = "codex.roomDemoUnityProofCapture.v1",
                capturedAt = DateTime.UtcNow.ToString("o"),
                valid = errors.Count == 0,
                importCapture = importCapture ?? string.Empty,
                cleanSceneCapture = cleanCapture ?? string.Empty,
                assetCount = assets.Count,
                importedAssetCount = assets.FindAll(asset => asset.imported).Count,
                assets = assets.ToArray(),
                warnings = warnings.ToArray(),
                errors = errors.ToArray(),
            };
        }

        private static void WriteReport(string reportPath, ProofCaptureReport report)
        {
            var parent = Path.GetDirectoryName(reportPath);
            if (!string.IsNullOrWhiteSpace(parent))
            {
                Directory.CreateDirectory(parent);
            }
            File.WriteAllText(reportPath, JsonUtility.ToJson(report, true));
        }

        private static string GetHierarchyPath(Transform transform)
        {
            var names = new List<string>();
            var current = transform;
            while (current != null)
            {
                names.Add(current.name);
                current = current.parent;
            }
            names.Reverse();
            return string.Join("/", names);
        }

        private static string SanitizeFileName(string value)
        {
            if (string.IsNullOrWhiteSpace(value)) return "asset";
            var chars = value.ToCharArray();
            for (var i = 0; i < chars.Length; i++)
            {
                var c = chars[i];
                if (!char.IsLetterOrDigit(c) && c != '_' && c != '-' && c != '.')
                {
                    chars[i] = '_';
                }
            }
            return new string(chars).Trim('.', '_', '-');
        }

        private static string GetCommandLineValue(string name)
        {
            var args = Environment.GetCommandLineArgs();
            for (var i = 0; i < args.Length - 1; i++)
            {
                if (string.Equals(args[i], name, StringComparison.OrdinalIgnoreCase))
                {
                    return args[i + 1];
                }
            }
            return string.Empty;
        }

        [Serializable]
        private class SelectedReferenceList
        {
            public SelectedReferencePayload[] items = Array.Empty<SelectedReferencePayload>();
        }

        [Serializable]
        private class SelectedReferencePayload
        {
            public string assetName = string.Empty;
            public string profile = string.Empty;
            public string role = string.Empty;
        }

        [Serializable]
        private class ProofCaptureReport
        {
            public string schema = string.Empty;
            public string capturedAt = string.Empty;
            public bool valid;
            public string importCapture = string.Empty;
            public string cleanSceneCapture = string.Empty;
            public int assetCount;
            public int importedAssetCount;
            public ProofAssetReport[] assets = Array.Empty<ProofAssetReport>();
            public string[] warnings = Array.Empty<string>();
            public string[] errors = Array.Empty<string>();
        }

        [Serializable]
        private class ProofAssetReport
        {
            public string assetName = string.Empty;
            public string profile = string.Empty;
            public string role = string.Empty;
            public bool imported;
            public string manifestPath = string.Empty;
            public string sceneObjectPath = string.Empty;
            public string[] errors = Array.Empty<string>();
        }
    }
}
