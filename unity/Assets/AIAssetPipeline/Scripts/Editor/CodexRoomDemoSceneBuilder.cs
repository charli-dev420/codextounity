using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace AIAssetFactory.EditorTools
{
    public static class CodexRoomDemoSceneBuilder
    {
        private const string DefaultScenePath = AIAssetConstants.GeneratedFolder + "/Scenes/CodexRoomDemoValidation.unity";
        private const string DefaultPrefabPath = AIAssetConstants.GeneratedFolder + "/Scenes/CodexRoomDemoRoot.prefab";

        public static void BuildFromCommandLine()
        {
            var selectedReferences = GetCommandLineValue("-codexRoomSelectedReferences");
            var manifestDir = GetCommandLineValue("-codexRoomManifestDir");
            var scenePath = GetCommandLineValue("-codexRoomScenePath");
            var prefabPath = GetCommandLineValue("-codexRoomPrefabPath");
            var reportPath = GetCommandLineValue("-codexRoomReport");

            if (string.IsNullOrWhiteSpace(scenePath)) scenePath = DefaultScenePath;
            if (string.IsNullOrWhiteSpace(prefabPath)) prefabPath = DefaultPrefabPath;
            if (string.IsNullOrWhiteSpace(reportPath))
            {
                reportPath = Path.Combine(Application.dataPath, "../CodexRoomDemoSceneBuilderReport.json");
            }

            var report = Build(selectedReferences, manifestDir, scenePath, prefabPath);
            WriteReport(reportPath, report);
            if (report.errors != null && report.errors.Length > 0)
            {
                foreach (var error in report.errors)
                {
                    Debug.LogError($"[AIAssetFactory] Room demo scene builder: {error}");
                }
                EditorApplication.Exit(2);
                return;
            }

            Debug.Log($"[AIAssetFactory] Room demo scene built: {report.scenePath}");
            EditorApplication.Exit(0);
        }

        private static RoomDemoSceneBuildReport Build(string selectedReferencesPath, string manifestDir, string scenePath, string prefabPath)
        {
            var errors = new List<string>();
            var warnings = new List<string>();
            var assets = new List<RoomDemoAssetReport>();
            var importedCount = 0;

            if (string.IsNullOrWhiteSpace(selectedReferencesPath) || !File.Exists(selectedReferencesPath))
            {
                errors.Add($"selected_references.json not found: {selectedReferencesPath}");
                return BuildReport(selectedReferencesPath, manifestDir, scenePath, prefabPath, importedCount, assets, errors, warnings);
            }

            if (string.IsNullOrWhiteSpace(manifestDir) || !Directory.Exists(manifestDir))
            {
                errors.Add($"manifest directory not found: {manifestDir}");
                return BuildReport(selectedReferencesPath, manifestDir, scenePath, prefabPath, importedCount, assets, errors, warnings);
            }

            var references = LoadSelectedReferences(selectedReferencesPath, errors);
            if (references.Length == 0)
            {
                errors.Add("selected_references.json contains no assets");
                return BuildReport(selectedReferencesPath, manifestDir, scenePath, prefabPath, importedCount, assets, errors, warnings);
            }

            Directory.CreateDirectory(Path.GetDirectoryName(scenePath) ?? AIAssetConstants.GeneratedFolder);
            Directory.CreateDirectory(Path.GetDirectoryName(prefabPath) ?? AIAssetConstants.GeneratedFolder);

            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            ConfigureSceneLighting();
            var root = new GameObject("CodexRoomDemoRoot");
            CreateNeutralFloor(root.transform);
            CreateCamera();

            foreach (var reference in references)
            {
                var assetReport = new RoomDemoAssetReport
                {
                    assetName = reference.assetName,
                    profile = reference.profile,
                    subProfile = reference.subProfile,
                    role = reference.role,
                    category = reference.category,
                };
                assets.Add(assetReport);

                if (string.IsNullOrWhiteSpace(reference.assetName))
                {
                    assetReport.errors = new[] { "assetName is missing" };
                    errors.Add("selected reference has no assetName");
                    continue;
                }

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
                var assetPrefab = imported as GameObject;
                if (assetPrefab == null)
                {
                    var importedType = imported == null ? "null" : imported.GetType().Name;
                    var message = $"imported asset is {importedType}, not a GameObject for {reference.assetName}; Unity may be missing a GLB importer package";
                    assetReport.errors = new[] { message };
                    errors.Add(message);
                    continue;
                }

                var instance = PrefabUtility.InstantiatePrefab(assetPrefab) as GameObject;
                if (instance == null)
                {
                    instance = UnityEngine.Object.Instantiate(assetPrefab);
                }

                instance.name = reference.assetName;
                instance.transform.SetParent(root.transform, false);
                ApplyPlacement(instance.transform, reference.unityPlacement);
                assetReport.sceneObjectPath = GetHierarchyPath(instance.transform);
                assetReport.position = instance.transform.position;
                assetReport.rotationEuler = instance.transform.eulerAngles;
                assetReport.uniformScale = instance.transform.localScale.x;
                assetReport.imported = true;
                importedCount++;
            }

            EditorSceneManager.MarkSceneDirty(scene);
            if (!EditorSceneManager.SaveScene(scene, scenePath))
            {
                errors.Add($"failed to save scene: {scenePath}");
            }

            var rootPrefab = PrefabUtility.SaveAsPrefabAsset(root, prefabPath);
            if (rootPrefab == null)
            {
                errors.Add($"failed to save root prefab: {prefabPath}");
            }

            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
            return BuildReport(selectedReferencesPath, manifestDir, scenePath, prefabPath, importedCount, assets, errors, warnings);
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

        private static void ConfigureSceneLighting()
        {
            RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Flat;
            RenderSettings.ambientLight = new Color(0.62f, 0.64f, 0.66f);
            var lightObject = new GameObject("CodexRoomDemo_KeyLight");
            var light = lightObject.AddComponent<Light>();
            light.type = LightType.Directional;
            light.intensity = 1.15f;
            lightObject.transform.rotation = Quaternion.Euler(50f, -35f, 0f);
        }

        private static void CreateNeutralFloor(Transform root)
        {
            var floor = GameObject.CreatePrimitive(PrimitiveType.Plane);
            floor.name = "CodexRoomDemo_NeutralFloor";
            floor.transform.SetParent(root, false);
            floor.transform.position = Vector3.zero;
            floor.transform.localScale = new Vector3(0.65f, 1f, 0.65f);
            var renderer = floor.GetComponent<Renderer>();
            if (renderer != null)
            {
                var material = new Material(Shader.Find("Standard"));
                material.name = "CodexRoomDemo_NeutralFloor_Material";
                material.color = new Color(0.56f, 0.56f, 0.53f);
                renderer.sharedMaterial = material;
            }
        }

        private static void CreateCamera()
        {
            var cameraObject = new GameObject("CodexRoomDemo_Camera");
            var camera = cameraObject.AddComponent<Camera>();
            camera.orthographic = true;
            camera.orthographicSize = 3.2f;
            camera.nearClipPlane = 0.1f;
            camera.farClipPlane = 100f;
            cameraObject.transform.position = new Vector3(4.8f, 3.6f, -5.2f);
            cameraObject.transform.rotation = Quaternion.Euler(35f, -42f, 0f);
            cameraObject.tag = "MainCamera";
            SceneView.lastActiveSceneView?.AlignViewToObject(cameraObject.transform);
        }

        private static void ApplyPlacement(Transform transform, PlacementPayload placement)
        {
            var position = placement?.position == null ? Vector3.zero : placement.position.ToVector3();
            var rotation = placement?.rotationEuler == null ? Vector3.zero : placement.rotationEuler.ToVector3();
            var scale = placement == null || placement.uniformScale <= 0f ? 1f : placement.uniformScale;
            transform.localPosition = position;
            transform.localRotation = Quaternion.Euler(rotation);
            transform.localScale = Vector3.one * scale;
        }

        private static string FindManifest(string manifestDir, string assetName)
        {
            var safeName = SanitizeFileName(assetName);
            var exact = Path.Combine(manifestDir, safeName + ".unity_manifest.json");
            if (File.Exists(exact)) return exact;

            var direct = Path.Combine(manifestDir, assetName + ".unity_manifest.json");
            if (File.Exists(direct)) return direct;

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

        private static RoomDemoSceneBuildReport BuildReport(
            string selectedReferencesPath,
            string manifestDir,
            string scenePath,
            string prefabPath,
            int importedCount,
            List<RoomDemoAssetReport> assets,
            List<string> errors,
            List<string> warnings)
        {
            return new RoomDemoSceneBuildReport
            {
                schema = "codex.roomDemoUnitySceneBuild.v1",
                builtAt = DateTime.UtcNow.ToString("o"),
                selectedReferences = selectedReferencesPath ?? string.Empty,
                manifestDir = manifestDir ?? string.Empty,
                scenePath = scenePath ?? string.Empty,
                rootPrefabPath = prefabPath ?? string.Empty,
                importedAssetCount = importedCount,
                assetCount = assets.Count,
                assets = assets.ToArray(),
                warnings = warnings.ToArray(),
                errors = errors.ToArray(),
                valid = errors.Count == 0,
            };
        }

        private static void WriteReport(string reportPath, RoomDemoSceneBuildReport report)
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
            public string subProfile = string.Empty;
            public string role = string.Empty;
            public string category = string.Empty;
            public PlacementPayload unityPlacement = new PlacementPayload();
        }

        [Serializable]
        private class PlacementPayload
        {
            public VectorPayload position = new VectorPayload();
            public VectorPayload rotationEuler = new VectorPayload();
            public float uniformScale = 1f;
        }

        [Serializable]
        private class VectorPayload
        {
            public float x;
            public float y;
            public float z;

            public Vector3 ToVector3()
            {
                return new Vector3(x, y, z);
            }
        }

        [Serializable]
        private class RoomDemoSceneBuildReport
        {
            public string schema = string.Empty;
            public string builtAt = string.Empty;
            public bool valid;
            public string selectedReferences = string.Empty;
            public string manifestDir = string.Empty;
            public string scenePath = string.Empty;
            public string rootPrefabPath = string.Empty;
            public int assetCount;
            public int importedAssetCount;
            public RoomDemoAssetReport[] assets = Array.Empty<RoomDemoAssetReport>();
            public string[] warnings = Array.Empty<string>();
            public string[] errors = Array.Empty<string>();
        }

        [Serializable]
        private class RoomDemoAssetReport
        {
            public string assetName = string.Empty;
            public string profile = string.Empty;
            public string subProfile = string.Empty;
            public string role = string.Empty;
            public string category = string.Empty;
            public bool imported;
            public string manifestPath = string.Empty;
            public string sceneObjectPath = string.Empty;
            public Vector3 position;
            public Vector3 rotationEuler;
            public float uniformScale;
            public string[] errors = Array.Empty<string>();
        }
    }
}
