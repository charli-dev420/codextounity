using System;
using System.IO;
using UnityEngine;

namespace AIAssetFactory
{
    [Serializable]
    public class AIAssetResult
    {
        public string jobId = string.Empty;
        public string requestId = string.Empty;
        public AIAssetStatus status = AIAssetStatus.DraftRequest;

        public string sourceImagenReferenceImage = string.Empty;
        public string comfyWorkflow = "trellis2_lowpoly_workflow.json";
        public string generationProfile = "SafeLowMemory";

        public string rawMesh = string.Empty;
        public string processedMesh = string.Empty;
        public string unityReadyMesh = string.Empty;

        public int triangleCount;
        public int vertexCount;
        public int subMeshCount;
        public int materialCount;

        public Vector3 rawBoundsMeters = Vector3.zero;
        public Vector3 normalizedBoundsMeters = Vector3.zero;
        public Vector3 targetBoundsMeters = Vector3.zero;
        public float uniformScale = 1f;
        public Vector3 rotationCorrectionEuler = Vector3.zero;
        public Vector3 offsetLocal = Vector3.zero;
        public float boundsDeviationPercent;
        public string socketClearanceStatus = "Pending";
        public string reportPath = string.Empty;

        public string hardwareProfile = "local_default";
        public string validationProfile = "SmallProp";
        public string resourceReportPath = string.Empty;

        public string importManifestPath = string.Empty;
        public bool validationPassed;
        public string[] validationErrors = new string[0];
        public string[] validationWarnings = new string[0];

        public static string GetResultPath(string jobId)
        {
            return $"{AIAssetConstants.ResultsFolder}/{jobId}.json";
        }

        public string ToJson() => JsonUtility.ToJson(this, true);

        public static AIAssetResult FromJson(string json) => JsonUtility.FromJson<AIAssetResult>(json);

        public void Write()
        {
            if (!Directory.Exists(AIAssetConstants.ResultsFolder))
                Directory.CreateDirectory(AIAssetConstants.ResultsFolder);
            File.WriteAllText(GetResultPath(jobId), ToJson());
        }

        public static AIAssetResult Read(string jobId)
        {
            var p = GetResultPath(jobId);
            return File.Exists(p) ? FromJson(File.ReadAllText(p)) : null;
        }
    }
}

