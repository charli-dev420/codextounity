using System;
using System.IO;
using UnityEngine;

namespace AIAssetFactory
{
    [Serializable]
    public class AIAssetRequest
    {
        public string requestId = string.Empty;
        public string assetId = string.Empty;
        public string sourcePrefabId = string.Empty;
        public string sourcePrefabPath = string.Empty;
        public string category = "Prop";
        public string zoneId = string.Empty;
        public string zoneTheme = string.Empty;
        public Vector3 targetSizeMeters = Vector3.one;
        public string pivotMode = "BottomCenter";
        public string forwardAxis = "+Z";
        public string upAxis = "+Y";
        public string replaceTarget = "VisualRoot";
        public string validationProfile = "SmallProp";
        public string fitMode = "FitInsideTargetBounds";
        public string visualStyle = "low-poly sci-fi industrial mobile game asset";
        public string generationProfile = "SafeLowMemory";
        public string comfyWorkflow = "trellis2_low-poly.ui.json";
        public int maxTriangles = 3000;
        public int maxMaterials = 2;
        public int maxTextureSize = 1024;
        public string[] mustPreserve = { "overall dimensions", "mobile readability" };
        public string[] mustAvoid = { "wrong scale", "thin fragile details" };
        public string[] referenceImages = new string[0];
        public string imagenPromptPath = string.Empty;
        public string imageGuidance = string.Empty;
        public string negativePrompt = string.Empty;
        public AIAssetStatus status = AIAssetStatus.DraftRequest;

        public static string GetRequestPath(string requestId)
        {
            return $"{AIAssetConstants.RequestsFolder}/{requestId}.json";
        }

        public string ToJson()
        {
            return JsonUtility.ToJson(this, true);
        }

        public static AIAssetRequest FromJson(string json)
        {
            return JsonUtility.FromJson<AIAssetRequest>(json);
        }

        public void Write()
        {
            EnsureDirectory();
            File.WriteAllText(GetRequestPath(requestId), ToJson());
        }

        public static AIAssetRequest Read(string requestId)
        {
            var p = GetRequestPath(requestId);
            if (!File.Exists(p)) return null;
            return FromJson(File.ReadAllText(p));
        }

        private static void EnsureDirectory()
        {
            if (!Directory.Exists(AIAssetConstants.RequestsFolder))
                Directory.CreateDirectory(AIAssetConstants.RequestsFolder);
        }
    }
}
