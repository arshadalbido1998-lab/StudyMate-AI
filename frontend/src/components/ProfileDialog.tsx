import { useEffect, useState, type FormEvent } from "react";
import type { User } from "@supabase/supabase-js";
import { supabase } from "../Lib/supabase";
import "./ProfileDialog.css";

type ProfileDialogProps = {
  user: User;
  userName: string;
  avatarUrl: string | null;
  loggingOut: boolean;
  logoutError: string;
  onClose: () => void;
  onLogout: () => void;
  onProfileUpdated: (user: User) => void;
};

function getInitials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase() || "S";
}

export default function ProfileDialog({
  user,
  userName,
  avatarUrl,
  loggingOut,
  logoutError,
  onClose,
  onLogout,
  onProfileUpdated,
}: ProfileDialogProps) {
  const [displayName, setDisplayName] = useState(userName);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [avatarFailed, setAvatarFailed] = useState(false);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextName = displayName.trim();
    if (!nextName) {
      setError("Please enter a display name.");
      return;
    }

    setError("");
    setSaved(false);
    setSaving(true);

    try {
      const { data, error: updateError } = await supabase.auth.updateUser({
        data: { full_name: nextName },
      });
      if (updateError) throw updateError;
      onProfileUpdated(data.user);
      setDisplayName(nextName);
      setSaved(true);
    } catch (updateError) {
      setError(
        updateError instanceof Error
          ? updateError.message
          : "We couldn't save your display name. Please try again.",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="profile-overlay" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section
        className="profile-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="profile-title"
      >
        <button
          className="profile-dialog__close"
          type="button"
          aria-label="Close profile"
          onClick={onClose}
        >
          ×
        </button>

        <p className="profile-dialog__eyebrow">YOUR ACCOUNT</p>
        <h2 id="profile-title">Profile settings</h2>

        <div className="profile-dialog__identity">
          <div className="profile-dialog__avatar" aria-hidden="true">
            {avatarUrl && !avatarFailed ? (
              <img
                src={avatarUrl}
                alt=""
                referrerPolicy="no-referrer"
                onError={() => setAvatarFailed(true)}
              />
            ) : (
              <span>{getInitials(userName)}</span>
            )}
          </div>
          <div className="profile-dialog__identity-copy">
            <strong>{userName}</strong>
            <span>{user.email || "No email address available"}</span>
          </div>
        </div>

        <form className="profile-dialog__form" onSubmit={handleSubmit}>
          <label htmlFor="profile-display-name">Display name</label>
          <div className="profile-dialog__input-row">
            <input
              id="profile-display-name"
              name="displayName"
              type="text"
              autoComplete="name"
              value={displayName}
              maxLength={120}
              onChange={(event) => {
                setDisplayName(event.target.value);
                setSaved(false);
                setError("");
              }}
              required
            />
            <button type="submit" disabled={saving || !displayName.trim()}>
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
          {error && <p className="profile-dialog__message profile-dialog__message--error" role="alert">{error}</p>}
          {saved && <p className="profile-dialog__message profile-dialog__message--success" role="status">Your display name has been updated.</p>}
        </form>

        <div className="profile-dialog__footer">
          <span>Your name appears in your StudyMate welcome screen.</span>
          <button
            className="profile-dialog__logout"
            type="button"
            onClick={onLogout}
            disabled={loggingOut}
          >
            {loggingOut ? "Signing out…" : "Log out"}
          </button>
          {logoutError && <p className="profile-dialog__message profile-dialog__message--error" role="alert">{logoutError}</p>}
        </div>
      </section>
    </div>
  );
}
