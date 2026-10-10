import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Runbooks and agent-generated text go through here: raw HTML is never rendered,
// images are dropped, and only http(s) links are clickable. Wrap it in `.markdown-body` for styling.
const components = {
  a: ({ href, children }) =>
    /^https?:/.test(href ?? "") ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> : <span>{children}</span>,
  img: () => null,
};

export default function SafeMarkdown({ children }) {
  return <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{String(children ?? "")}</ReactMarkdown>;
}
