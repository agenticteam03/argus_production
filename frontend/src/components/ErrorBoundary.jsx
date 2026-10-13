import { Component } from "react";
import { ErrorCard } from "./ui.jsx";

// When a render throws and nothing catches it, React unmounts the whole tree: the app goes blank and only the
// page background is left. This keeps the shell (header and nav) alive and turns the crash into a visible,
// retryable message. Key it on the route so navigating away clears the error. React needs a class for this.
export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Page render failed", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <ErrorCard
          title="This page couldn't be displayed"
          text="Something went wrong while drawing this page. The error was logged to the browser console."
          onRetry={() => this.setState({ error: null })}
        />
      );
    }
    return this.props.children;
  }
}
