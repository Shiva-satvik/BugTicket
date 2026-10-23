
import { useEffect, useRef, useState } from "react";
import { Camera, ShieldCheck, Trash2, Upload, X, ExternalLink } from "lucide-react";
import { PageHeader } from "../components/Common.jsx";
import { authApi, errorMessage } from "../api/services";
import { fmt, getUserName, initials, safeArray } from "../utils";

function photoUrl(path) {
  if (!path) return "";

  if (/^https?:\/\//i.test(path)) {
    return path;
  }

  const base = (
    import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
  ).replace(/\/+$/, "");

  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}

export default function ProfilePage({ user, onUserUpdated }) {
  const fileInput = useRef(null);

  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [photoPreviewOpen, setPhotoPreviewOpen] = useState(false);
  const [imageFailed, setImageFailed] = useState(false);

  const roles = safeArray(user?.roles)
    .map((role) =>
      typeof role === "object"
        ? role?.name || role?.role || ""
        : role
    )
    .filter(Boolean);

  const profileDetails = [
    ["Username", user?.username],
    ["Email", user?.email],
    ["Employee ID", user?.employee_id],
    ["Department", user?.department_name ?? user?.department_id],
    ["Designation", user?.designation],
    [
      "Roles",
      roles.length ? roles.join(", ") : "Loaded from access policy",
    ],
  ];

  useEffect(() => {
    setImageFailed(false);
  }, [user?.photo_url]);

  useEffect(() => {
    if (!photoPreviewOpen) return;

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setPhotoPreviewOpen(false);
      }
    }

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [photoPreviewOpen]);

  async function uploadPhoto(event) {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file) return;

    setError("");
    setMessage("");

    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      setError("Choose a JPG, PNG, or WebP image.");
      return;
    }

    if (file.size === 0) {
      setError("The selected image is empty.");
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      setError("The profile photo must be 5 MB or smaller.");
      return;
    }

    if (typeof authApi.uploadPhoto !== "function") {
      setError("Photo upload API is unavailable. Check src/api/services.js.");
      return;
    }

    setBusy(true);

    try {
      const { data } = await authApi.uploadPhoto(file);

      onUserUpdated?.({
        ...user,
        photo_url: data.photo_url || null,
      });

      setImageFailed(false);
      setMessage("Profile photo updated successfully.");
    } catch (err) {
      setError(errorMessage(err, "Could not upload your profile photo."));
    } finally {
      setBusy(false);
    }
  }

  async function removePhoto() {
    if (!user?.photo_url || busy) return;

    setBusy(true);
    setError("");
    setMessage("");

    try {
      const { data } = await authApi.removePhoto();

      setPhotoPreviewOpen(false);
      setImageFailed(false);

      onUserUpdated?.({
        ...user,
        photo_url: data.photo_url || null,
      });

      setMessage("Profile photo removed successfully.");
    } catch (err) {
      setError(errorMessage(err, "Could not remove your profile photo."));
    } finally {
      setBusy(false);
    }
  }

  const imageSrc = photoUrl(user?.photo_url);
  const canViewPhoto = Boolean(user?.photo_url) && !imageFailed;

  return (
    <>
      <PageHeader
        eyebrow="ACCOUNT"
        title="Your profile"
        description="Manage your profile photo and review your identity and access information."
      />

      <section className="panel profile-panel">
        <div className="profile-heading">
          <button
            type="button"
            className="avatar avatar-large"
            onClick={() => {
              if (canViewPhoto) setPhotoPreviewOpen(true);
            }}
            disabled={!canViewPhoto}
            title={canViewPhoto ? "Click to view full-size photo" : undefined}
            aria-label="View full-size profile photo"
            style={{
              overflow: "hidden",
              padding: 0,
              border: 0,
              cursor: canViewPhoto ? "pointer" : "default",
              flexShrink: 0,
            }}
          >
            {canViewPhoto ? (
              <img
                src={imageSrc}
                alt={`${getUserName(user)} profile`}
                onError={() => setImageFailed(true)}
                style={{
                  width: "100%",
                  height: "100%",
                  objectFit: "cover",
                  display: "block",
                }}
              />
            ) : (
              initials(getUserName(user))
            )}
          </button>

          <div>
            <h2>{getUserName(user)}</h2>
            <p>{user?.designation || "BugPilot member"}</p>

            <div
              style={{
                display: "flex",
                gap: 8,
                flexWrap: "wrap",
                marginTop: 10,
              }}
            >
              <button
                type="button"
                className="button button-secondary"
                onClick={() => fileInput.current?.click()}
                disabled={busy}
              >
                {busy ? <span className="spinner" /> : <Camera size={16} />}
                {busy ? "Saving…" : "Upload photo"}
              </button>

              {user?.photo_url && (
                <button
                  type="button"
                  className="button button-secondary"
                  onClick={removePhoto}
                  disabled={busy}
                >
                  <Trash2 size={16} />
                  Remove photo
                </button>
              )}

              <input
                ref={fileInput}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={uploadPhoto}
                hidden
                disabled={busy}
              />
            </div>

            <small style={{ display: "block", marginTop: 8 }}>
              JPG, PNG, or WebP · Maximum 5 MB
            </small>
          </div>

          <span className="profile-active">
            <span />
            Authenticated
          </span>
        </div>

        {error && (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        )}

        {message && (
          <div className="alert alert-success" role="status">
            <Upload size={16} />
            {message}
          </div>
        )}

        <div className="profile-details">
          {profileDetails.map(([label, value]) => (
            <div key={label}>
              <span>{label}</span>
              <b>{fmt(value)}</b>
            </div>
          ))}
        </div>

        <div className="profile-note">
          <ShieldCheck size={17} />
          <span>
            Role-based permissions are enforced by the backend.
            This page does not grant additional access.
          </span>
        </div>
      </section>

      {photoPreviewOpen && canViewPhoto && (
        <div
          onClick={() => setPhotoPreviewOpen(false)}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 9999,
            background: "rgba(0, 0, 0, 0.78)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 20,
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Profile photo preview"
            onClick={(event) => event.stopPropagation()}
            style={{
              position: "relative",
              maxWidth: "92vw",
              maxHeight: "92vh",
              padding: 12,
              borderRadius: 16,
              background: "var(--panel-bg, #ffffff)",
              boxShadow: "0 20px 70px rgba(0,0,0,0.3)",
            }}
          >
            <button
              type="button"
              onClick={() => setPhotoPreviewOpen(false)}
              aria-label="Close photo preview"
              className="button button-secondary"
              style={{
                position: "absolute",
                top: 18,
                right: 18,
                zIndex: 1,
                background: "rgba(0,0,0,0.75)",
                color: "#fff",
                borderColor: "transparent",
                padding: 8,
              }}
            >
              <X size={20} />
            </button>

            <img
              src={imageSrc}
              alt={`${getUserName(user)} full-size profile`}
              onError={() => {
                setImageFailed(true);
                setPhotoPreviewOpen(false);
                setError("Could not load the full-size photo.");
              }}
              style={{
                display: "block",
                maxWidth: "85vw",
                maxHeight: "78vh",
                width: "auto",
                height: "auto",
                objectFit: "contain",
                borderRadius: 10,
              }}
            />

            <div style={{ padding: "12px 4px 2px" }}>
              <a
                href={imageSrc}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  color: "inherit",
                  textDecoration: "none",
                }}
              >
                <ExternalLink size={16} />
                Open original photo in new tab
              </a>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
