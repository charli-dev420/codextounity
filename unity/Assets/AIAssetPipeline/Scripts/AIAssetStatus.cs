namespace AIAssetFactory
{
    public enum AIAssetStatus
    {
        DraftRequest,
        AwaitingImagenReference,
        ImagenReady,
        WaitingForResources,
        WaitingForGpuLock,
        SentToComfy,
        RunningComfyTrellis,
        RunningPostProcess,
        RunningNormalization,
        RunningValidation,
        RunningUnityImport,
        Generated,
        Normalized,
        ValidationPassed,
        ValidationFailed,
        Imported,
        Previewed,
        Accepted,
        Rejected,
        FailedOOM,
        FailedTimeout,
        FailedComfyUnavailable,
        FailedInsufficientResources,
        Cancelled,
        NeedsManualRetry,
        NeedsManualReview,
        NeedsImporter,
        Error
    }
}

