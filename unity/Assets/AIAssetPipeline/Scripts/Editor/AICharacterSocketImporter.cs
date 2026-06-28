using System;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace AIAssetFactory.EditorTools
{
    public static class AICharacterSocketImporter
    {
        [Serializable]
        private class SocketManifest
        {
            public string characterId;
            public string rigName;
            public SocketSlot[] slots;
            public SocketSlot[] sockets;
        }

        [Serializable]
        private class SocketSlot
        {
            public string slotId;
            public string name;
            public string attachmentKey;
            public string stableKey;
            public string bone;
            public float[] position;
            public float[] localPosition;
            public float[] rotationEuler;
            public float[] localRotationEuler;
            public float[] scale;
            public float[] localScale;
            public string equipmentCategory;
            public string previewPose;
            public string notes;
        }

        [MenuItem(AIAssetConstants.MenuRoot + "/Import Character Attachment Manifest")]
        public static void ImportCharacterAttachmentManifest()
        {
            var root = Selection.activeGameObject;
            if (root == null)
            {
                Debug.LogError("[AIAssetFactory] Select the character root before importing sockets.");
                return;
            }

            var path = EditorUtility.OpenFilePanel("Import character attachment manifest", Application.dataPath, "json");
            if (string.IsNullOrWhiteSpace(path) || !File.Exists(path)) return;

            var manifest = JsonUtility.FromJson<SocketManifest>(File.ReadAllText(path));
            if (manifest == null)
            {
                Debug.LogError($"[AIAssetFactory] Invalid socket manifest: {path}");
                return;
            }

            var slots = manifest.slots != null && manifest.slots.Length > 0 ? manifest.slots : manifest.sockets;
            if (slots == null || slots.Length == 0)
            {
                Debug.LogError($"[AIAssetFactory] No slots found in socket manifest: {path}");
                return;
            }

            var created = 0;
            foreach (var slot in slots)
            {
                if (slot == null || string.IsNullOrWhiteSpace(slot.slotId)) continue;
                var bone = FindChildByName(root.transform, slot.bone);
                if (bone == null)
                {
                    Debug.LogWarning($"[AIAssetFactory] Bone not found for slot {slot.slotId}: {slot.bone}");
                    continue;
                }

                var socketName = string.IsNullOrWhiteSpace(slot.name) ? $"Socket_{slot.slotId}" : slot.name;
                var existing = bone.Find(socketName);
                var socket = existing != null ? existing.gameObject : new GameObject(socketName);
                if (existing == null) Undo.RegisterCreatedObjectUndo(socket, "Create character socket");
                else Undo.RecordObject(socket.transform, "Update character socket");

                socket.transform.SetParent(bone, false);
                socket.transform.localPosition = ToVector3(slot.localPosition, ToVector3(slot.position, Vector3.zero));
                socket.transform.localRotation = Quaternion.Euler(ToVector3(slot.localRotationEuler, ToVector3(slot.rotationEuler, Vector3.zero)));
                socket.transform.localScale = ToVector3(slot.localScale, ToVector3(slot.scale, Vector3.one));
                var marker = socket.GetComponent<AICharacterAttachmentSocket>();
                if (marker == null) marker = Undo.AddComponent<AICharacterAttachmentSocket>(socket);
                Undo.RecordObject(marker, "Update character socket metadata");
                marker.characterId = manifest.characterId;
                marker.slotId = slot.slotId;
                marker.attachmentKey = string.IsNullOrWhiteSpace(slot.attachmentKey) ? $"{manifest.characterId}:{slot.slotId}" : slot.attachmentKey;
                marker.bone = slot.bone;
                marker.equipmentCategory = slot.equipmentCategory;
                marker.previewPose = slot.previewPose;
                marker.notes = slot.notes;
                marker.authoredLocalPosition = socket.transform.localPosition;
                marker.authoredLocalRotationEuler = ToVector3(slot.localRotationEuler, ToVector3(slot.rotationEuler, Vector3.zero));
                marker.authoredLocalScale = socket.transform.localScale;
                EditorUtility.SetDirty(marker);
                created++;
            }

            EditorUtility.SetDirty(root);
            Debug.Log($"[AIAssetFactory] Imported {created} character sockets from {Path.GetFileName(path)} onto {root.name}.");
        }

        private static Vector3 ToVector3(float[] values, Vector3 fallback)
        {
            if (values == null || values.Length < 3) return fallback;
            return new Vector3(values[0], values[1], values[2]);
        }

        private static Transform FindChildByName(Transform root, string childName)
        {
            if (root == null || string.IsNullOrWhiteSpace(childName)) return null;
            if (string.Equals(root.name, childName, StringComparison.OrdinalIgnoreCase)) return root;
            foreach (Transform child in root)
            {
                var found = FindChildByName(child, childName);
                if (found != null) return found;
            }
            return null;
        }
    }
}
