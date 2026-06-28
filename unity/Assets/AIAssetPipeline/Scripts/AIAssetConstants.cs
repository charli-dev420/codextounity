using UnityEngine;

namespace AIAssetFactory
{
    public static class AIAssetConstants
    {
        public const string PipName = "Codex Asset Pipeline";
        public const string RootFolder = "Assets/AIAssetPipeline";
        public const string ScriptsFolder = RootFolder + "/Scripts";
        public const string RequestsFolder = RootFolder + "/Data/Requests";
        public const string ResultsFolder = RootFolder + "/Data/Results";
        public const string ProfilesFolder = RootFolder + "/Data/Profiles";
        public const string ReportsFolder = RootFolder + "/Reports";
        public const string GeneratedFolder = RootFolder + "/Generated";
        public const string ReportsResourceFolder = ReportsFolder + "/Resources";
        public const string ReportsNormalizationFolder = ReportsFolder + "/Normalization";
        public const string ReferenceFolder = GeneratedFolder + "/ReferenceImages";
        public const string Raw3DFolder = GeneratedFolder + "/Raw3D";
        public const string Processed3DFolder = GeneratedFolder + "/Processed3D";
        public const string UnityReadyFolder = GeneratedFolder + "/UnityReady";
        public const string MenuRoot = "Tools/Codex Asset Pipeline";

        public const string PrefabDefaultProfile = "SafeLowMemory";
        public const string POCMenuRoot = MenuRoot;
        public const int HttpTimeoutMs = 20000;

        public const string LastJobIdEditorPref = "AIAssetFactory.LastJobId";
    }
}
