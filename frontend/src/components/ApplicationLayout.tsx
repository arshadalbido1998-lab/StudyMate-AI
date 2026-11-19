import { useState, type PropsWithChildren } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import type { User } from "@supabase/supabase-js";
import type { StudyChatMessage } from "../api";
import RecentConversations, { type ConversationItem } from "./RecentConversations";
import Navigation from "./Navigation";
import "./ApplicationLayout.css";

type ApplicationLayoutProps = PropsWithChildren<{
  pageTitle: string;
  isChatWorkspace: boolean;
  isMindMapWorkspace: boolean;
  user: User;
  userId: string;
  userName: string;
  avatarUrl: string | null;
  onLogout: () => void;
  loggingOut: boolean;
  logoutError: string;
  onProfileUpdated: (user: User) => void;
  conversations: ConversationItem[];
  conversationLoadError: string;
  conversationsLoading: boolean;
  activeConversationId: string | null;
  onNewChat: () => void;
  onOpenChat: (messages: StudyChatMessage[], historyId: string) => void;
  onDeleteChat: (historyId: string) => void;
}>;

const navigationItems = [
  {
    to: "/chat",
    label: "Chat",
    icon: <><path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H7l-4 2v-5.5A7.5 7.5 0 1 1 20 11.5Z" /><path d="M8 10h8M8 14h5" /></>,
  },
  {
    to: "/mind-map",
    label: "Mind Map",
    icon: <><circle cx="12" cy="12" r="2.5" /><circle cx="5" cy="5" r="1.5" /><circle cx="19" cy="5" r="1.5" /><circle cx="5" cy="19" r="1.5" /><circle cx="19" cy="19" r="1.5" /><path d="m10.2 10.2-4.1-4.1m7.7 4.1 4.1-4.1m-7.7 7.7-4.1 4.1m7.7-4.1 4.1 4.1" /></>,
  },
  {
    to: "/practice",
    label: "Practice",
    icon: <><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8M8 12h8M8 16h4" /></>,
  },
  {
    to: "/study-planner",
    label: "Study Planner",
    icon: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18M8 14h3m-3 3h7" /></>,
  },
];

export default function ApplicationLayout({
  children,
  pageTitle,
  isChatWorkspace,
  isMindMapWorkspace,
  user,
  userId,
  userName,
  avatarUrl,
  onLogout,
  loggingOut,
  logoutError,
  onProfileUpdated,
  conversations,
  conversationLoadError,
  conversationsLoading,
  activeConversationId,
  onNewChat,
  onOpenChat,
  onDeleteChat,
}: ApplicationLayoutProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const navigate = useNavigate();

  const closeMobileNavigation = () => setMobileOpen(false);
  const startNewChat = () => {
    onNewChat();
    navigate("/chat");
    closeMobileNavigation();
  };
  const openChat = (messages: StudyChatMessage[], historyId: string) => {
    onOpenChat(messages, historyId);
    navigate("/chat");
    closeMobileNavigation();
  };

  return (
    <div
      className={`workspace-shell${isChatWorkspace ? " is-chat-workspace" : ""}${isMindMapWorkspace ? " is-mind-map-workspace" : ""}${collapsed ? " is-collapsed" : ""}${mobileOpen ? " is-mobile-open" : ""}`}
    >
      <button
        className="workspace-sidebar-backdrop"
        type="button"
        aria-label="Close navigation"
        tabIndex={mobileOpen ? 0 : -1}
        onClick={closeMobileNavigation}
      />
      <aside className="workspace-sidebar" aria-label="StudyMate AI workspace">
        <NavLink
          to="/chat"
          className="workspace-brand"
          aria-label="StudyMate AI, Chat workspace"
          onClick={closeMobileNavigation}
        >
          <span className="workspace-brand__mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M5 18V6h3l4 6 4-6h3v12h-3V11l-4 5-4-5v7H5Z" />
            </svg>
          </span>
          <span className="workspace-brand__name">StudyMate <b>AI</b></span>
        </NavLink>

        <nav className="workspace-navigation" aria-label="Primary">
          <span className="workspace-navigation__label">Workspace</span>
          {navigationItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `workspace-navigation__link${isActive ? " is-active" : ""}`
              }
              aria-label={item.label}
              onClick={closeMobileNavigation}
              title={collapsed ? item.label : undefined}
            >
              <svg
                className="workspace-navigation__icon"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                {item.icon}
              </svg>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <RecentConversations
          userId={userId}
          conversations={conversations}
          loadError={conversationLoadError}
          isLoading={conversationsLoading}
          activeConversationId={activeConversationId}
          onNewChat={startNewChat}
          onOpenChat={openChat}
          onDeleteChat={onDeleteChat}
        />

        <button
          className="workspace-sidebar__collapse"
          type="button"
          onClick={() => setCollapsed((value) => !value)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <rect x="3" y="4" width="18" height="16" rx="2" />
            <path d={collapsed ? "M9 4v16m5-11 3 3-3 3" : "M9 4v16m5-8h3"} />
          </svg>
          <span>{collapsed ? "Expand sidebar" : "Collapse sidebar"}</span>
        </button>
      </aside>

      <div className="workspace-main">
        <header className="workspace-topbar">
          <button
            className="workspace-mobile-toggle"
            type="button"
            aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={mobileOpen}
            onClick={() => setMobileOpen((value) => !value)}
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              aria-hidden="true"
            >
              {mobileOpen
                ? <path d="m6 6 12 12M18 6 6 18" />
                : <path d="M4 7h16M4 12h16M4 17h16" />}
            </svg>
          </button>
          <div className="workspace-topbar__title">
            <span>StudyMate AI</span>
            <h1>{pageTitle}</h1>
          </div>
          <Navigation
            user={user}
            userName={userName}
            avatarUrl={avatarUrl}
            onLogout={onLogout}
            loggingOut={loggingOut}
            logoutError={logoutError}
            onProfileUpdated={onProfileUpdated}
          />
        </header>
        <main className="workspace-content">{children}</main>
      </div>
    </div>
  );
}
