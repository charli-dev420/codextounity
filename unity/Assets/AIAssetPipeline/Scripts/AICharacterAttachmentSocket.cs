using UnityEngine;

namespace AIAssetFactory
{
    public sealed class AICharacterAttachmentSocket : MonoBehaviour
    {
        public string characterId;
        public string slotId;
        public string attachmentKey;
        public string bone;
        public string equipmentCategory;
        public string previewPose;
        [TextArea]
        public string notes;
        public Vector3 authoredLocalPosition;
        public Vector3 authoredLocalRotationEuler;
        public Vector3 authoredLocalScale = Vector3.one;

        public static AICharacterAttachmentSocket Find(Transform root, string characterId, string slotId)
        {
            if (root == null || string.IsNullOrWhiteSpace(characterId) || string.IsNullOrWhiteSpace(slotId)) return null;
            var key = characterId + ":" + slotId;
            foreach (var socket in root.GetComponentsInChildren<AICharacterAttachmentSocket>(true))
            {
                if (socket == null) continue;
                if (socket.attachmentKey == key) return socket;
                if (socket.characterId == characterId && socket.slotId == slotId) return socket;
            }
            return null;
        }
    }
}
