import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { supabase } from "../Lib/supabase";
import "./Auth.css";

type AuthProps = {
  error: string;
};

type AuthMode = "login" | "signup";

function getRedirectError(): string {
  const params = new URLSearchParams(
    `${window.location.search.slice(1)}&${window.location.hash.slice(1)}`,
  );
  const error = params.get("error_description") ?? params.get("error");
  return error ?? "";
}

function readableAuthError(message: string): string {
  if (message.includes("Invalid login credentials")) {
    return "That email and password combination wasn't recognized.";
  }
  if (message.includes("User already registered")) {
    return "An account with this email already exists. Try signing in instead.";
  }
  return message;
}

export default function Auth({ error: sessionError }: AuthProps) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const redirectError = getRedirectError();
    if (redirectError) {
      setError(readableAuthError(redirectError));
    }
  }, []);

  const switchMode = (nextMode: AuthMode) => {
    setMode(nextMode);
    setError("");
    setMessage("");
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setMessage("");
    setLoading(true);

    try {
      if (mode === "signup") {
        const { data, error: signUpError } = await supabase.auth.signUp({
          email,
          password,
          options: {
            data: { full_name: fullName.trim() },
          },
        });

        if (signUpError) throw signUpError;
        if (!data.session) {
          setMessage(
            "Your account was created. Check your email for a confirmation link, then return here to sign in.",
          );
        }
      } else {
        const { error: signInError } = await supabase.auth.signInWithPassword({
          email,
          password,
        });

        if (signInError) throw signInError;
      }
    } catch (authError) {
      setError(
        readableAuthError(
          authError instanceof Error
            ? authError.message
            : "We couldn't complete that request. Please try again.",
        ),
      );
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
    setError("");
    setMessage("");
    setLoading(true);

    try {
      const { error: oauthError } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: window.location.origin },
      });

      if (oauthError) throw oauthError;
    } catch (authError) {
      setError(
        readableAuthError(
          authError instanceof Error
            ? authError.message
            : "Google sign-in couldn't be started. Please try again.",
        ),
      );
      setLoading(false);
    }
  };

  return (
    <main className="auth-screen">
      <section className="auth-card" aria-labelledby="auth-title">
        <Link className="auth-brand" to="/chat" aria-label="StudyMate AI home">
          <span className="auth-brand__mark">S</span>
          <span>StudyMate <b>AI</b></span>
        </Link>

        <div className="auth-card__intro">
          <span className="auth-eyebrow">YOUR LEARNING SPACE</span>
          <h1 id="auth-title">
            {mode === "login" ? "Welcome back." : "Start learning smarter."}
          </h1>
          <p>
            {mode === "login"
              ? "Sign in to pick up where your next breakthrough begins."
              : "Create an account to make every study session count."}
          </p>
        </div>

        <div className="auth-tabs" role="tablist" aria-label="Account access">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "login"}
            className={mode === "login" ? "is-active" : ""}
            onClick={() => switchMode("login")}
          >
            Sign in
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "signup"}
            className={mode === "signup" ? "is-active" : ""}
            onClick={() => switchMode("signup")}
          >
            Create account
          </button>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          {mode === "signup" && (
            <label>
              Full name
              <input
                type="text"
                name="fullName"
                autoComplete="name"
                placeholder="Your name"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                required
                maxLength={120}
              />
            </label>
          )}
          <label>
            Email
            <input
              type="email"
              name="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              name="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              placeholder="Enter your password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={6}
            />
          </label>

          {(error || sessionError) && (
            <p className="auth-message auth-message--error" role="alert">
              {error || readableAuthError(sessionError)}
            </p>
          )}
          {message && (
            <p className="auth-message auth-message--success" role="status">
              {message}
            </p>
          )}

          <button className="auth-submit" type="submit" disabled={loading}>
            {loading ? (
              <>
                <span className="auth-button-spinner" aria-hidden="true" />
                {mode === "login" ? "Signing in…" : "Creating account…"}
              </>
            ) : mode === "login" ? (
              "Sign in"
            ) : (
              "Create account"
            )}
          </button>
        </form>

        <div className="auth-divider"><span>or continue with</span></div>
        <button
          className="auth-google"
          type="button"
          onClick={handleGoogleLogin}
          disabled={loading}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.75 3.27-8.1Z" />
            <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.65l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.15v2.84A11 11 0 0 0 12 23Z" />
            <path fill="currentColor" d="M5.84 14.11a6.6 6.6 0 0 1 0-4.22V7.05H2.15a11 11 0 0 0 0 9.9l3.69-2.84Z" />
            <path fill="currentColor" d="M12 4.36c1.62 0 3.06.56 4.21 1.64l3.15-3.15A10.53 10.53 0 0 0 12 0 11 11 0 0 0 2.15 7.05l3.69 2.84C6.71 7.29 9.14 4.36 12 4.36Z" />
          </svg>
          Continue with Google
        </button>

        <p className="auth-legal">
          By continuing, you agree to use StudyMate AI as your personal study
          companion.
        </p>
      </section>
    </main>
  );
}
