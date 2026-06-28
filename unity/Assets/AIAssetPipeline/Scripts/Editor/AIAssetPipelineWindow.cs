using UnityEditor;
using UnityEngine;

namespace AIAssetFactory.EditorTools
{
    public class AIAssetPipelineWindow : EditorWindow
    {
        [MenuItem(AIAssetConstants.MenuRoot + "/Pipeline Window")]
        private static void Open()
        {
            var window = GetWindow<AIAssetPipelineWindow>("Codex Asset Pipeline");
            window.minSize = new Vector2(420, 280);
            window.Show();
        }

        private void OnGUI()
        {
            GUILayout.Label("Codex Asset Pipeline", EditorStyles.boldLabel);

            EditorGUILayout.Space(6);
            GUILayout.Label("Request", EditorStyles.boldLabel);
            if (GUILayout.Button("Create Request From Selected Prefab")) AIAssetPipelineCommands.CreateRequestFromSelectedPrefab();
            if (GUILayout.Button("Build Reference Prompt From Request")) AIAssetPipelineCommands.BuildReferencePromptFromRequest();
            if (GUILayout.Button("Attach Reference Image")) AIAssetPipelineCommands.AttachReferenceImage();

            EditorGUILayout.Space(6);
            GUILayout.Label("Codex Output", EditorStyles.boldLabel);
            if (GUILayout.Button("Import Codex Result Manifest")) AIAssetPipelineCommands.ImportResultManifest();

            EditorGUILayout.Space(6);
            GUILayout.Label("Folders", EditorStyles.boldLabel);
            if (GUILayout.Button("Open Requests")) AIAssetPipelineCommands.OpenRequestsFolder();
            if (GUILayout.Button("Open Results")) AIAssetPipelineCommands.OpenResultsFolder();
            if (GUILayout.Button("Open Generated Assets")) AIAssetPipelineCommands.OpenGeneratedFolder();
        }
    }
}
