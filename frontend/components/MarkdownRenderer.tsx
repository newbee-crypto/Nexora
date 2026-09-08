import React from "react";
import { MessageSquare, Phone, Mail, Award } from "lucide-react";

interface MarkdownRendererProps {
  content: string;
}

interface Block {
  type: "paragraph" | "heading" | "list" | "table";
  text?: string;
  level?: number;
  ordered?: boolean;
  items?: string[];
  headers?: string[];
  alignments?: ("left" | "center" | "right")[];
  rows?: string[][];
}

// Custom parser to split markdown text into structured blocks
export function parseMarkdown(text: string): Block[] {
  const lines = text.split("\n");
  const blocks: Block[] = [];
  let currentTable: { headers: string[]; alignments: ("left" | "center" | "right")[]; rows: string[][] } | null = null;
  let currentList: { ordered: boolean; items: string[] } | null = null;
  let currentParagraph: string[] = [];

  const flushParagraph = () => {
    if (currentParagraph.length > 0) {
      blocks.push({ type: "paragraph", text: currentParagraph.join("\n") });
      currentParagraph = [];
    }
  };

  const flushList = () => {
    if (currentList) {
      blocks.push({ type: "list", ordered: currentList.ordered, items: currentList.items });
      currentList = null;
    }
  };

  const flushTable = () => {
    if (currentTable) {
      blocks.push({
        type: "table",
        headers: currentTable.headers,
        alignments: currentTable.alignments,
        rows: currentTable.rows,
      });
      currentTable = null;
    }
  };

  const flushAll = () => {
    flushParagraph();
    flushList();
    flushTable();
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // 1. Table Parsing
    if (trimmed.startsWith("|") && (trimmed.endsWith("|") || currentTable !== null)) {
      flushParagraph();
      flushList();

      const rawParts = trimmed.split("|");
      if (rawParts[0] === "") rawParts.shift();
      if (rawParts[rawParts.length - 1] === "") rawParts.pop();
      const parts = rawParts.map((s) => s.trim());

      if (!currentTable) {
        // Look ahead for separator line: e.g. |---|---|
        const nextLine = (lines[i + 1] || "").trim();
        if (nextLine.startsWith("|") && nextLine.endsWith("|") && nextLine.replace(/[\s|:\-]/g, "") === "") {
          const alignments = nextLine
            .split("|")
            .map((s) => s.trim())
            .filter((_, idx, arr) => idx > 0 && idx < arr.length - 1)
            .map((cell) => {
              const left = cell.startsWith(":");
              const right = cell.endsWith(":");
              if (left && right) return "center" as const;
              if (right) return "right" as const;
              return "left" as const;
            });

          currentTable = {
            headers: parts,
            alignments: alignments,
            rows: [],
          };
          i++; // Skip the divider line
        } else {
          currentParagraph.push(line);
        }
      } else {
        // Pad row parts to match headers length
        while (parts.length < currentTable.headers.length) {
          parts.push("");
        }
        currentTable.rows.push(parts);
      }
      continue;
    }

    if (currentTable) {
      flushTable();
    }

    // 2. Heading Parsing
    const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      flushAll();
      blocks.push({
        type: "heading",
        level: headingMatch[1].length,
        text: headingMatch[2],
      });
      continue;
    }

    // 3. List Item Parsing
    const listMatch = trimmed.match(/^([\*\-\+])\s+(.*)$/);
    if (listMatch) {
      flushParagraph();
      const itemText = listMatch[2];
      if (currentList && !currentList.ordered) {
        currentList.items.push(itemText);
      } else {
        flushList();
        currentList = { ordered: false, items: [itemText] };
      }
      continue;
    }

    const orderedListMatch = trimmed.match(/^(\d+)\.\s+(.*)$/);
    if (orderedListMatch) {
      flushParagraph();
      const itemText = orderedListMatch[2];
      if (currentList && currentList.ordered) {
        currentList.items.push(itemText);
      } else {
        flushList();
        currentList = { ordered: true, items: [itemText] };
      }
      continue;
    }

    if (currentList) {
      if (line.startsWith("  ") && currentList.items.length > 0) {
        currentList.items[currentList.items.length - 1] += "\n" + trimmed;
        continue;
      } else {
        flushList();
      }
    }

    // 4. Blank Line
    if (trimmed === "") {
      flushAll();
      continue;
    }

    // 5. Paragraph
    currentParagraph.push(line);
  }

  flushAll();
  return blocks;
}

// Format bold (**), code (`), and italic (*) inline tags
export function formatInlineText(text: string): React.ReactNode[] {
  if (!text) return [];

  // Match bold (**text**), code (`text`), italic (*text*)
  const regex = /(\*\*.*?\*\*|`.*?`|\*.*?\*)/g;
  const parts = text.split(regex);

  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={index} className="font-semibold text-zinc-950">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code
          key={index}
          className="font-mono text-[10px] bg-zinc-100 border border-zinc-200 rounded px-1.5 py-0.5 text-indigo-600 font-semibold"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith("*") && part.endsWith("*")) {
      return (
        <em key={index} className="italic text-zinc-800">
          {part.slice(1, -1)}
        </em>
      );
    }
    return part;
  });
}

export default function MarkdownRenderer({ content }: MarkdownRendererProps) {
  const blocks = parseMarkdown(content);

  const renderTableCell = (header: string, text: string) => {
    const trimmed = text.trim();

    // 1. Rank / Number styling
    if (header.toLowerCase() === "rank" || header === "#") {
      const val = parseInt(trimmed, 10);
      if (val === 1) {
        return (
          <span className="inline-flex items-center gap-1 rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-bold text-amber-700 border border-amber-200 shadow-3xs">
            <Award className="h-3 w-3 text-amber-500 fill-amber-500" />
            1st
          </span>
        );
      }
      if (val === 2) {
        return (
          <span className="inline-flex items-center gap-1 rounded bg-slate-50 px-1.5 py-0.5 text-[10px] font-bold text-slate-700 border border-slate-200 shadow-3xs">
            <Award className="h-3 w-3 text-slate-400 fill-slate-400" />
            2nd
          </span>
        );
      }
      if (val === 3) {
        return (
          <span className="inline-flex items-center gap-1 rounded bg-amber-50/30 px-1.5 py-0.5 text-[10px] font-bold text-amber-650 border border-amber-200/50">
            <Award className="h-3 w-3 text-amber-600/80" />
            3rd
          </span>
        );
      }
      return <span className="font-semibold text-zinc-500 pl-1">{trimmed}</span>;
    }

    // 2. Channel Badging
    if (header.toLowerCase().includes("channel")) {
      const channelVal = trimmed.toLowerCase();
      if (channelVal === "whatsapp") {
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-[10px] font-semibold text-emerald-700 border border-emerald-200/60 shadow-3xs">
            <Phone className="h-2.5 w-2.5 fill-emerald-500 text-emerald-500" />
            WhatsApp
          </span>
        );
      }
      if (channelVal === "sms") {
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-sky-50 px-2.5 py-0.5 text-[10px] font-semibold text-sky-700 border border-sky-200/60 shadow-3xs">
            <MessageSquare className="h-2.5 w-2.5 fill-sky-500 text-sky-500" />
            SMS
          </span>
        );
      }
      if (channelVal === "email") {
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-purple-50 px-2.5 py-0.5 text-[10px] font-semibold text-purple-700 border border-purple-200/60 shadow-3xs">
            <Mail className="h-2.5 w-2.5 fill-purple-400 text-purple-500" />
            Email
          </span>
        );
      }
    }

    // 3. Date Check
    if (trimmed.match(/^\d{4}-\d{2}-\d{2}$/)) {
      return (
        <span className="font-mono text-zinc-500 font-semibold text-[10px]">
          {trimmed}
        </span>
      );
    }

    // 4. Currency Check
    if (trimmed.startsWith("₹") || trimmed.startsWith("$")) {
      return (
        <span className="font-semibold text-zinc-900 font-mono text-[11px]">
          {trimmed}
        </span>
      );
    }

    return formatInlineText(trimmed);
  };

  return (
    <div className="space-y-3">
      {blocks.map((block, index) => {
        switch (block.type) {
          case "heading": {
            const level = block.level || 1;
            const text = block.text || "";
            const formatted = formatInlineText(text);

            if (level === 1) return <h1 key={index} className="text-base font-extrabold text-zinc-950 tracking-tight my-3">{formatted}</h1>;
            if (level === 2) return <h2 key={index} className="text-sm font-bold text-zinc-950 tracking-tight my-2.5">{formatted}</h2>;
            if (level === 3) return <h3 key={index} className="text-xs font-bold text-zinc-900 tracking-tight my-2">{formatted}</h3>;
            return <h4 key={index} className="text-2xs font-semibold text-zinc-900 my-1.5">{formatted}</h4>;
          }

          case "list": {
            const items = block.items || [];
            const Tag = block.ordered ? "ol" : "ul";
            const tagClass = block.ordered
              ? "list-decimal pl-5 space-y-1.5 my-2.5 text-zinc-700 text-xs"
              : "list-disc pl-5 space-y-1.5 my-2.5 text-zinc-700 text-xs";

            return (
              <Tag key={index} className={tagClass}>
                {items.map((item, iIdx) => (
                  <li key={iIdx} className="leading-relaxed">
                    {formatInlineText(item)}
                  </li>
                ))}
              </Tag>
            );
          }

          case "table": {
            const headers = block.headers || [];
            const alignments = block.alignments || [];
            const rows = block.rows || [];

            return (
              <div key={index} className="w-full my-4 overflow-x-auto rounded-xl border border-zinc-200/80 bg-white shadow-3xs">
                <table className="min-w-full divide-y divide-zinc-200 text-left text-[11px] leading-normal">
                  <thead className="bg-zinc-50/80 font-semibold text-zinc-600 uppercase text-[9px] tracking-wider border-b border-zinc-150">
                    <tr>
                      {headers.map((header, hIdx) => {
                        const alignment = alignments[hIdx] || "left";
                        const alignClass =
                          alignment === "right"
                            ? "text-right"
                            : alignment === "center"
                            ? "text-center"
                            : "text-left";
                        return (
                          <th key={hIdx} className={`px-4 py-3 ${alignClass} font-semibold text-zinc-500`}>
                            {header}
                          </th>
                        );
                      })}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-150 bg-white">
                    {rows.map((row, rIdx) => (
                      <tr
                        key={rIdx}
                        className="hover:bg-zinc-50/40 transition-colors odd:bg-white even:bg-zinc-50/20"
                      >
                        {row.map((cell, cIdx) => {
                          const alignment = alignments[cIdx] || "left";
                          const alignClass =
                            alignment === "right"
                              ? "text-right"
                              : alignment === "center"
                              ? "text-center"
                              : "text-left";
                          const header = headers[cIdx] || "";
                          return (
                            <td key={cIdx} className={`px-4 py-2.5 ${alignClass} align-middle text-zinc-700`}>
                              {renderTableCell(header, cell)}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          }

          case "paragraph":
          default: {
            const text = block.text || "";
            // If the paragraph is empty, return null
            if (!text.trim()) return null;

            return (
              <p key={index} className="whitespace-pre-wrap leading-relaxed">
                {formatInlineText(text)}
              </p>
            );
          }
        }
      })}
    </div>
  );
}
