import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

/** GFM for the tables the agent produces when it lists orders; sanitize because model output
 *  is untrusted text on its way into the DOM. */
export function Markdown({ text }: { text: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>
      {text}
    </ReactMarkdown>
  );
}
