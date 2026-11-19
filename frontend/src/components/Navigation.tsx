import { useCallback, useEffect, useState } from "react";
import type { User } from "@supabase/supabase-js";
import ProfileDialog from "./ProfileDialog";
import "./Navigation.css";

type NavigationProps = {
  user: User;
  userName: string;
  avatarUrl: string | null;
  onLogout: () => void;
  loggingOut: boolean;
  logoutError: string;
  onProfileUpdated: (user: User) => void;
};

export default function Navigation({
  user,
  userName,
  avatarUrl,
  onLogout,
  loggingOut,
  logoutError,
  onProfileUpdated,
}: NavigationProps) {
  const [profileOpen, setProfileOpen] = useState(false);
  const [avatarFailed, setAvatarFailed] = useState(false);

  useEffect(() => {
    setAvatarFailed(false);
  }, [avatarUrl]);

  const closeProfile = useCallback(() => setProfileOpen(false), []);

  return (
    <div className="workspace-account">
      <div className="workspace-account__details">
        <button
          className="workspace-account__profile"
          type="button"
          onClick={() => setProfileOpen(true)}
          aria-label="Open profile settings"
        >
          <span className="workspace-account__avatar" aria-hidden="true">
            {avatarUrl && !avatarFailed ? (
              <img
                src={avatarUrl}
                alt=""
                referrerPolicy="no-referrer"
                onError={() => setAvatarFailed(true)}
              />
            ) : (
              userName.slice(0, 1).toUpperCase()
            )}
          </span>
          <span className="workspace-account__name">{userName}</span>
        </button>
        <button
          className="workspace-account__logout"
          type="button"
          onClick={onLogout}
          disabled={loggingOut}
        >
          {loggingOut ? "Signing out…" : "Log out"}
        </button>
        {logoutError && (
          <span className="workspace-account__error" role="alert">
            {logoutError}
          </span>
        )}
      </div>
      {profileOpen && (
        <ProfileDialog
          user={user}
          userName={userName}
          avatarUrl={avatarUrl}
          loggingOut={loggingOut}
          logoutError={logoutError}
          onClose={closeProfile}
          onLogout={onLogout}
          onProfileUpdated={onProfileUpdated}
        />
      )}
    </div>
  );
}
