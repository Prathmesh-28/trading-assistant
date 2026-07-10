import { Component, type ReactNode } from "react";

interface State {
  error: Error | null;
}

/** Last line of defense: a crash anywhere renders a readable card with a
 * reload button instead of a black screen. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="loading-screen">
          <div className="loading-box">
            <p style={{ fontWeight: 700 }}>Something broke on this screen.</p>
            <p className="loading-hint">
              {String(this.state.error.message || this.state.error).slice(0, 200)}
            </p>
            <p className="loading-hint">
              This usually means the app and the server are on different versions —
              redeploy the backend on Render, then reload.
            </p>
            <button
              className="btn-big btn-buy"
              style={{ marginTop: 12 }}
              onClick={() => {
                this.setState({ error: null });
                window.location.reload();
              }}
            >
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
