using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace AIAssetFactory.EditorTools
{
    public static class AIAssetResultImporter
    {
        [MenuItem(AIAssetConstants.MenuRoot + "/Import Result From Manifest")]
        public static void Import()
        {
            var path = EditorUtility.OpenFilePanel("Import AIAsset manifest", AIAssetConstants.ResultsFolder, "json");
            if (string.IsNullOrWhiteSpace(path))
            {
                return;
            }

            ImportManifest(path);
        }

        public static void ImportManifest(string path)
        {
            ImportManifest(path, false);
        }

        public static UnityEngine.Object ImportManifestForAutomation(string path)
        {
            return ImportManifestForAutomation(path, false);
        }

        public static UnityEngine.Object ImportManifestForAutomation(string path, bool addToScene)
        {
            return ImportManifestInternal(path, addToScene, true);
        }

        [MenuItem(AIAssetConstants.MenuRoot + "/Import Result And Add To Scene")]
        public static void ImportAndAddToScene()
        {
            var path = EditorUtility.OpenFilePanel("Import AIAsset manifest and add to scene", AIAssetConstants.ResultsFolder, "json");
            if (string.IsNullOrWhiteSpace(path))
            {
                return;
            }

            ImportManifest(path, true);
        }

        public static void ImportManifestFromCommandLine()
        {
            var manifestPath = GetCommandLineValue("-aiAssetManifest");
            if (string.IsNullOrWhiteSpace(manifestPath))
            {
                Debug.LogError("[AIAssetFactory] Missing -aiAssetManifest <path>.");
                return;
            }

            ImportManifest(manifestPath, HasCommandLineFlag("-aiAssetAddToScene"));
        }

        public static void ImportManifest(string path, bool addToScene)
        {
            ImportManifestInternal(path, addToScene, false);
        }

        private static UnityEngine.Object ImportManifestInternal(string path, bool addToScene, bool automationMode)
        {
            if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
            {
                Debug.LogError($"[AIAssetFactory] Manifest not found: {path}");
                return null;
            }

            var text = File.ReadAllText(path);
            var manifest = JsonUtility.FromJson<AIAssetManifestPayload>(text);
            string meshPath = null;
            if (manifest != null)
            {
                if (ManifestNeedsReview(manifest))
                {
                    if (automationMode)
                    {
                        Debug.LogWarning($"[AIAssetFactory] Automation import continues with validation issues: {path}");
                    }
                    else if (!ConfirmImportWithValidationIssues(manifest))
                    {
                        Debug.LogWarning($"[AIAssetFactory] Import cancelled for manifest with validation issues: {path}");
                        return null;
                    }
                }

                meshPath = !string.IsNullOrWhiteSpace(manifest.generatedMesh) ? manifest.generatedMesh : manifest.unityReadyMesh;
                if (string.IsNullOrWhiteSpace(meshPath))
                {
                    meshPath = !string.IsNullOrWhiteSpace(manifest.processedMesh) ? manifest.processedMesh : manifest.rawMesh;
                }
            }

            if (string.IsNullOrWhiteSpace(meshPath))
            {
                var fallback = JsonUtility.FromJson<AIAssetResult>(text);
                if (fallback != null && !string.IsNullOrWhiteSpace(fallback.unityReadyMesh))
                {
                    meshPath = fallback.unityReadyMesh;
                }
                else if (fallback != null && !string.IsNullOrWhiteSpace(fallback.processedMesh))
                {
                    meshPath = fallback.processedMesh;
                }
                else if (fallback != null && !string.IsNullOrWhiteSpace(fallback.rawMesh))
                {
                    meshPath = fallback.rawMesh;
                }
            }

            if (string.IsNullOrWhiteSpace(meshPath))
            {
                Debug.LogWarning($"[AIAssetFactory] No mesh path found in manifest: {path}");
                return null;
            }

            var unityPath = ConvertToUnityPath(meshPath);
            if (string.IsNullOrWhiteSpace(unityPath))
            {
                Debug.LogWarning($"[AIAssetFactory] Manifest path not inside project: {meshPath}");
                if (!automationMode)
                {
                    EditorUtility.RevealInFinder(path);
                }
                return null;
            }

            var assetDir = Path.GetDirectoryName(unityPath);
            if (!string.IsNullOrWhiteSpace(assetDir))
            {
                AssetDatabase.ImportAsset(assetDir, ImportAssetOptions.ImportRecursive | ImportAssetOptions.ForceUpdate);
            }
            else
            {
                AssetDatabase.ImportAsset(unityPath, ImportAssetOptions.ForceUpdate);
            }

            var importedGameObject = AssetDatabase.LoadAssetAtPath<GameObject>(unityPath);
            var imported = importedGameObject != null
                ? importedGameObject
                : AssetDatabase.LoadAssetAtPath<UnityEngine.Object>(unityPath);
            if (imported != null)
            {
                var selected = CreatePrefabAssetIfPossible(imported, unityPath, manifest) ?? imported;
                if (addToScene)
                {
                    AddImportedAssetToScene(selected, manifest);
                }
                else
                {
                    Selection.activeObject = selected;
                    EditorGUIUtility.PingObject(selected);
                }
                Debug.Log($"[AIAssetFactory] Imported asset: {unityPath}");
                return selected;
            }
            else
            {
                Debug.LogWarning($"[AIAssetFactory] Mesh file not found in Asset DB: {unityPath}");
                return null;
            }
        }

        private static UnityEngine.Object CreatePrefabAssetIfPossible(UnityEngine.Object imported, string unityPath, AIAssetManifestPayload manifest)
        {
            if (!(imported is GameObject source))
            {
                return null;
            }

            var prefabPath = ConvertToUnityPath(manifest?.unityPrefabPath);
            if (string.IsNullOrWhiteSpace(prefabPath))
            {
                var assetDir = Path.GetDirectoryName(unityPath);
                var prefabName = $"{Path.GetFileNameWithoutExtension(unityPath)}_unity_ready.prefab";
                prefabPath = string.IsNullOrWhiteSpace(assetDir) ? prefabName : $"{assetDir}/{prefabName}";
            }

            try
            {
                var instance = PrefabUtility.InstantiatePrefab(source) as GameObject;
                if (instance == null)
                {
                    instance = UnityEngine.Object.Instantiate(source);
                }

                instance.name = string.IsNullOrWhiteSpace(manifest?.assetId) ? Path.GetFileNameWithoutExtension(unityPath) : manifest.assetId;
                var prefab = PrefabUtility.SaveAsPrefabAsset(instance, prefabPath);
                UnityEngine.Object.DestroyImmediate(instance);
                AssetDatabase.ImportAsset(prefabPath, ImportAssetOptions.ForceUpdate);
                if (prefab != null)
                {
                    Debug.Log($"[AIAssetFactory] Unity-ready prefab: {prefabPath}");
                }
                return prefab;
            }
            catch (Exception error)
            {
                Debug.LogWarning($"[AIAssetFactory] Prefab creation failed for {unityPath}: {error.Message}");
                return null;
            }
        }

        private static void AddImportedAssetToScene(UnityEngine.Object imported, AIAssetManifestPayload manifest)
        {
            if (!(imported is GameObject prefab))
            {
                Debug.LogWarning($"[AIAssetFactory] Imported object is not a GameObject and cannot be added to scene: {imported}");
                return;
            }

            var instance = PrefabUtility.InstantiatePrefab(prefab) as GameObject;
            if (instance == null)
            {
                instance = UnityEngine.Object.Instantiate(prefab);
            }

            Undo.RegisterCreatedObjectUndo(instance, "Add AI asset to scene");
            instance.name = string.IsNullOrWhiteSpace(manifest?.assetId) ? prefab.name : manifest.assetId;
            instance.transform.position = Vector3.zero;
            instance.transform.rotation = Quaternion.identity;
            Selection.activeGameObject = instance;
            EditorGUIUtility.PingObject(instance);
            if (instance.scene.IsValid())
            {
                EditorSceneManager.MarkSceneDirty(instance.scene);
            }
            Debug.Log($"[AIAssetFactory] Added asset to active scene: {instance.name}");
        }

        private static bool ManifestNeedsReview(AIAssetManifestPayload manifest)
        {
            if (manifest == null)
            {
                return false;
            }

            if (manifest.validationErrors != null && manifest.validationErrors.Length > 0)
            {
                return true;
            }

            var status = manifest.status ?? string.Empty;
            if (string.IsNullOrWhiteSpace(status))
            {
                return false;
            }

            if (manifest.validationPassed || status.Equals("ValidationPassed", StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }

            return status.IndexOf("Failed", StringComparison.OrdinalIgnoreCase) >= 0
                || status.IndexOf("Error", StringComparison.OrdinalIgnoreCase) >= 0
                || status.Equals("NeedsManualReview", StringComparison.OrdinalIgnoreCase)
                || status.Equals("ValidationFailed", StringComparison.OrdinalIgnoreCase)
                || status.Equals("Rejected", StringComparison.OrdinalIgnoreCase);
        }

        private static bool ConfirmImportWithValidationIssues(AIAssetManifestPayload manifest)
        {
            var errors = manifest.validationErrors == null ? Array.Empty<string>() : manifest.validationErrors;
            var errorText = errors.Length == 0 ? "No validation error details were provided." : string.Join("\n", errors);
            var status = string.IsNullOrWhiteSpace(manifest.status) ? "unknown" : manifest.status;
            return EditorUtility.DisplayDialog(
                "Import Codex Manifest?",
                $"This manifest is not cleanly validated.\n\nStatus: {status}\n\n{errorText}",
                "Import Anyway",
                "Cancel");
        }

        private static string ConvertToUnityPath(string path)
        {
            if (string.IsNullOrWhiteSpace(path))
            {
                return string.Empty;
            }

            path = path.Replace('\\', '/');
            var marker = "Assets/";
            var index = path.IndexOf(marker, StringComparison.OrdinalIgnoreCase);
            if (index < 0)
            {
                if (!path.StartsWith(marker, StringComparison.OrdinalIgnoreCase))
                {
                    return string.Empty;
                }

                return path;
            }

            return path.Substring(index);
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

        private static bool HasCommandLineFlag(string name)
        {
            foreach (var arg in Environment.GetCommandLineArgs())
            {
                if (string.Equals(arg, name, StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }
            return false;
        }

        [Serializable]
        private class AIAssetManifestPayload
        {
            public string generatedMesh = string.Empty;
            public string assetId = string.Empty;
            public string unityReadyMesh = string.Empty;
            public string unityPrefabPath = string.Empty;
            public string processedMesh = string.Empty;
            public string rawMesh = string.Empty;
            public string status = string.Empty;
            public string requestId = string.Empty;
            public string jobId = string.Empty;
            public bool validationPassed;
            public string[] validationErrors = Array.Empty<string>();
            public string sourceImagenReferenceImage = string.Empty;
        }
    }
}
