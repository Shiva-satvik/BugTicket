import { useRef, useState } from "react";
import { Camera, ShieldCheck, Trash2, Upload } from "lucide-react";
import { PageHeader } from "../components/Common.jsx";
import { authApi, errorMessage } from "../api/services";
import { fmt, getUserName, initials, safeArray } from "../utils";

function photoUrl(path) {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  const base = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}

export default function ProfilePage({ user, onUserUpdated }) {
  const fileInput = useRef(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const roles = safeArray(user?.roles)
    .map((role) => (typeof role === "object" ? role?.name || role?.role || "" : role))
    .filter(Boolean);

  const profileDetails = [
    ["Username", user?.username],
    ["Email", user?.email],
    ["Employee ID", user?.employee_id],
    ["Department", user?.department_name ?? user?.department_id],
    ["Designation", user?.designation],
    ["Roles", roles.length > 0 ? roles.join(", ") : "Loaded from access policy"],
  ];

  async function uploadPhoto(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setError("");
    setMessage("");
    if (!/^image\/(jpeg|png|webp)$/.test(file.type)) {
      setError("Choose a JPG, PNG, or WebP image.");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setError("The profile photo must be 5 MB or smaller.");
      return;
    }
    setBusy(true);
    try {
      const { data } = await authApi.uploadPhoto(file);
      const updated = { ...user, photo_url: data.photo_url };
      onUserUpdated?.(updated);
      setMessage("Profile photo updated. It will remain saved when you sign in again.");
    } catch (err) {
      setError(errorMessage(err, "Could not upload your profile photo."));
    } finally {
      setBusy(false);
    }
  }

  async function removePhoto() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const { data } = await authApi.removePhoto();
      onUserUpdated?.({ ...user, photo_url: data.photo_url || null });
      setMessage("Profile photo removed.");
    } catch (err) {
      setError(errorMessage(err, "Could not remove your profile photo."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader eyebrow="ACCOUNT" title="Your profile" description="Manage your profile photo and review the identity and access information returned by BugPilot." />
      <section className="panel profile-panel">
        <div className="profile-heading">
          <div className="avatar avatar-large" style={{ overflow: "hidden", padding: 0 }}>
            {user?.photo_url ? <img src={photoUrl(user.photo_url)} alt={`${getUserName(user)} profile`} style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : initials(getUserName(user))}
          </div>
          <div>
            <h2>{getUserName(user)}</h2>
            <p>{user?.designation || "BugPilot member"}</p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
              <button type="button" className="button button-secondary" onClick={() => fileInput.current?.click()} disabled={busy}>
                {busy ? <span className="spinner" /> : <Camera size={16} />} {busy ? "Saving…" : "Upload photo"}
              </button>
              {user?.photo_url && <button type="button" className="button button-secondary" onClick={removePhoto} disabled={busy}><Trash2 size={16} /> Remove photo</button>}
              <input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" onChange={uploadPhoto} hidden />
            </div>
            <small style={{ display: "block", marginTop: 8 }}>JPG, PNG, or WebP · Maximum 5 MB</small>
          </div>
          <span className="profile-active"><span />Authenticated</span>
        </div>
        {error && <div className="alert alert-error" role="alert">{error}</div>}
        {message && <div className="alert alert-success" role="status"><Upload size={16} /> {message}</div>}
        <div className="profile-details">
          {profileDetails.map(([label, value]) => <div key={label}><span>{label}</span><b>{fmt(value)}</b></div>)}
        </div>
        <div className="profile-note"><ShieldCheck size={17} /><span>Role-based permissions are enforced by the backend. This page does not grant additional access.</span></div>
      </section>
    </>
  );
}
