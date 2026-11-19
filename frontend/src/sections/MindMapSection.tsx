import { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";
import { cancelMindMapGeneration, customizeMindMap, generateMindMap, getMindMapProgress, uploadNotes, type GeneratedMindMap, type MindMapProgress } from "../api";
import "./MindMapSection.css";

type Node = { id: string; label: string; description: string; kind: string; x: number; y: number; relationship?: string };
type Link = { from: string; to: string; kind: string };
type Point = { x: number; y: number };
const W = 2000;
const H = 1600;
const MIN_ZOOM = 0.01;
const MAX_ZOOM = 100;

function nodeSize(kind: string) {
  if (kind === "central") return { width: 280, height: 116 };
  if (kind === "topic") return { width: 250, height: 112 };
  return { width: 220, height: 112 };
}

function placeWithoutOverlap(nodes: Node[], candidate: Node): Node {
  const size = nodeSize(candidate.kind);
  for (let attempt = 0; attempt < 180; attempt += 1) {
    const ring = attempt === 0 ? 0 : 55 + Math.floor((attempt - 1) / 12) * 75;
    const angle = attempt * 2.399963229728653;
    const x = Math.max(size.width / 2 + 35, Math.min(W - size.width / 2 - 35, candidate.x + Math.cos(angle) * ring));
    const y = Math.max(size.height / 2 + 35, Math.min(H - size.height / 2 - 35, candidate.y + Math.sin(angle) * ring));
    const overlaps = nodes.some((node) => {
      const other = nodeSize(node.kind);
      return Math.abs(x - node.x) < (size.width + other.width) / 2 + 42
        && Math.abs(y - node.y) < (size.height + other.height) / 2 + 42;
    });
    if (!overlaps) return { ...candidate, x, y };
  }
  return candidate;
}

function graphFor(map: GeneratedMindMap, collapsed: Set<string>) {
  const nodes: Node[] = [{ ...map.central_topic, kind: "central", x: W / 2, y: H / 2 }];
  const links: Link[] = [];
  const radiusX = 500;
  const radiusY = 360;
  map.main_topics.forEach((topic, i) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / map.main_topics.length;
    const tx = W / 2 + Math.cos(angle) * radiusX;
    const ty = H / 2 + Math.sin(angle) * radiusY;
    const positionedTopic = placeWithoutOverlap(nodes, { ...topic, kind: "topic", x: tx, y: ty });
    nodes.push(positionedTopic);
    links.push({ from: "central", to: topic.id, kind: "hierarchy" });
    const children = collapsed.has(topic.id) ? [] : topic.subtopics;
    children.forEach((child, j) => {
      const spread = Math.min(0.72, 0.24 + children.length * 0.08);
      const a = angle + (j - (children.length - 1) / 2) * spread;
      const x = positionedTopic.x + Math.cos(a) * 310;
      const y = positionedTopic.y + Math.sin(a) * 310;
      nodes.push(placeWithoutOverlap(nodes, { ...child, kind: "subtopic", x, y }));
      links.push({ from: topic.id, to: child.id, kind: "hierarchy" });
    });
  });
  let byId = new Map(nodes.map((n) => [n.id, n]));
  map.related_concepts.forEach((concept, i) => {
    const targets = concept.related_to.map((id) => byId.get(id)).filter(Boolean) as Node[];
    if (targets.length < 2) return;
    const centerX = targets.reduce((s, n) => s + n.x, 0) / targets.length;
    const centerY = targets.reduce((s, n) => s + n.y, 0) / targets.length;
    const dx = targets[targets.length - 1].x - targets[0].x;
    const dy = targets[targets.length - 1].y - targets[0].y;
    const length = Math.max(1, Math.hypot(dx, dy));
    const direction = i % 2 ? 1 : -1;
    const candidate = {
      ...concept,
      kind: "related",
      x: centerX - (dy / length) * 190 * direction,
      y: centerY + (dx / length) * 190 * direction,
      relationship: concept.relationship,
    };
    nodes.push(placeWithoutOverlap(nodes, candidate));
    byId = new Map(nodes.map((node) => [node.id, node]));
    targets.forEach((target) => links.push({ from: target.id, to: concept.id, kind: "related" }));
  });
  return { nodes, links, byId, width: W, height: H };
}

function edgePath(from: Node, to: Node, index: number) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.max(1, Math.hypot(dx, dy));
  const ux = dx / length;
  const uy = dy / length;
  const edgeOffset = (node: Node) => {
    const { width, height } = nodeSize(node.kind);
    return Math.min(width / 2 / Math.max(Math.abs(ux), 0.001), height / 2 / Math.max(Math.abs(uy), 0.001));
  };
  const startOffset = edgeOffset(from);
  const endOffset = edgeOffset(to);
  const sx = from.x + ux * startOffset;
  const sy = from.y + uy * startOffset;
  const ex = to.x - ux * endOffset;
  const ey = to.y - uy * endOffset;
  const bend = index % 2 ? 22 : -22;
  const cx = (sx + ex) / 2 - uy * bend;
  const cy = (sy + ey) / 2 + ux * bend;
  return `M ${sx} ${sy} Q ${cx} ${cy} ${ex} ${ey}`;
}

const generationStages: Array<{ id: MindMapProgress["stage"]; label: string }> = [
  { id: "reading_document", label: "Reading document" },
  { id: "generating_branches", label: "Generating branches" },
  { id: "connecting_concepts", label: "Connecting concepts" },
  { id: "validating_mind_map", label: "Validating mind map" },
];

export default function MindMapSection() {
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [filename, setFilename] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [mindMap, setMindMap] = useState<GeneratedMindMap | null>(null);
  const [loading, setLoading] = useState(false);
  const [generationStage, setGenerationStage] = useState<MindMapProgress["stage"]>("reading_document");
  const [chunkProgress, setChunkProgress] = useState<{ completed: number; total: number } | null>(null);
  const [seenStages, setSeenStages] = useState<Set<string>>(new Set());
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [stopping, setStopping] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [draft, setDraft] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [selected, setSelected] = useState<Node | null>(null);
  const [nodePositions, setNodePositions] = useState<Record<string, Point>>({});
  const [draggedNodeId, setDraggedNodeId] = useState<string | null>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const canvas = useRef<SVGSVGElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const composerTextarea = useRef<HTMLTextAreaElement>(null);
  const canvasDrag = useRef<{ id: number; point: Point } | null>(null);
  const nodeDrag = useRef<{
    id: number;
    nodeId: string;
    start: Point;
    origin: Point;
    moved: boolean;
  } | null>(null);
  const suppressNodeClick = useRef<string | null>(null);
  const pendingFit = useRef(false);
  const fitGraphRef = useRef<() => void>(() => undefined);
  const generationVersion = useRef(0);
  const activeGeneration = useRef<{ id: string; controller: AbortController; version: number } | null>(null);
  const baseGraph = useMemo(() => mindMap ? graphFor(mindMap, collapsed) : null, [mindMap, collapsed]);
  const graph = useMemo(() => {
    if (!baseGraph) return null;
    const layout = baseGraph;
    const nodes = layout.nodes.map((node) => ({ ...node, ...nodePositions[node.id] }));
    return { ...layout, nodes, byId: new Map(nodes.map((node) => [node.id, node])) };
  }, [baseGraph, nodePositions]);

  const fitGraph = useCallback(() => {
    const view = viewport.current;
    if (!graph || !view || graph.nodes.length === 0) return;
    const bounds = graph.nodes.reduce((result, node) => {
      const size = nodeSize(node.kind);
      return {
        left: Math.min(result.left, node.x - size.width / 2),
        right: Math.max(result.right, node.x + size.width / 2),
        top: Math.min(result.top, node.y - size.height / 2),
        bottom: Math.max(result.bottom, node.y + size.height / 2),
      };
    }, { left: Infinity, right: -Infinity, top: Infinity, bottom: -Infinity });
    const rect = view.getBoundingClientRect();
    const screenScale = Math.min(rect.width / W, rect.height / H);
    if (!screenScale || !Number.isFinite(screenScale)) return;
    const zoomToFit = Math.min(
      (rect.width - 72) / ((bounds.right - bounds.left) * screenScale),
      (rect.height - 72) / ((bounds.bottom - bounds.top) * screenScale),
    );
    const nextZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoomToFit));
    const centerX = (bounds.left + bounds.right) / 2;
    const centerY = (bounds.top + bounds.bottom) / 2;
    setZoom(nextZoom);
    setPan({ x: W / 2 - centerX * nextZoom, y: H / 2 - centerY * nextZoom });
  }, [graph]);
  fitGraphRef.current = fitGraph;

  useLayoutEffect(() => {
    if (!graph || !pendingFit.current) return;
    const frame = window.requestAnimationFrame(() => {
      fitGraphRef.current();
      pendingFit.current = false;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [graph]);

  useLayoutEffect(() => {
    const textarea = composerTextarea.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
  }, [draft]);

  const toCanvasPoint = (clientX: number, clientY: number): Point | null => {
    const matrix = canvas.current?.getScreenCTM();
    if (!matrix) return null;
    const point = new DOMPoint(clientX, clientY).matrixTransform(matrix.inverse());
    return { x: point.x, y: point.y };
  };
  const chooseFile = async (file?: File) => {
    if (!file) return;
    if (!/\.(pdf|txt|md)$/i.test(file.name)) { setUploadError("Choose a PDF, TXT, or MD file."); return; }
    setUploading(true); setUploadError(""); setError(""); setNotice(""); setFilename(file.name); setMindMap(null); setDocumentId(null);
    setNodePositions({}); setSelected(null); setCollapsed(new Set()); setZoom(1); setPan({ x: 0, y: 0 });
    try { const result = await uploadNotes(file); setDocumentId(result.document_id); setFilename(result.filename); }
    catch (e) { setUploadError(e instanceof Error ? e.message : "Upload failed. Try again."); }
    finally { setUploading(false); }
  };
  const generate = async (instruction = draft) => {
    if (!documentId || loading || uploading) return;
    const initialInstruction = instruction.trim();
    const version = generationVersion.current + 1;
    generationVersion.current = version;
    const generationId = typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const controller = new AbortController();
    activeGeneration.current = { id: generationId, controller, version };
    setDraft(""); setLoading(true); setStopping(false); setError(""); setNotice(""); setGenerationStage("reading_document"); setChunkProgress(null);
    setSeenStages(new Set(["reading_document"])); setElapsedSeconds(0);
    const startedAt = Date.now();
    let timedOut = false;
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      void cancelMindMapGeneration(generationId).catch(() => undefined);
      controller.abort();
    }, 15 * 60 * 1000);
    const elapsedId = window.setInterval(
      () => setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000)),
      1000,
    );
    const pollProgress = async () => {
      while (!controller.signal.aborted) {
        try {
          const progress = await getMindMapProgress(documentId, controller.signal);
          if (progress.stage !== "complete" && progress.stage !== "failed") {
            setGenerationStage(progress.stage);
            setSeenStages((previous) => new Set(previous).add(progress.stage));
          }
          setElapsedSeconds(progress.elapsed_seconds);
          setChunkProgress(progress.completed_chunks != null && progress.total_chunks != null
            ? { completed: progress.completed_chunks, total: progress.total_chunks }
            : null);
        } catch {
          // The generation request remains authoritative; polling can recover.
        }
        await new Promise((resolve) => window.setTimeout(resolve, 800));
      }
    };
    void pollProgress();
    try {
      const generated = await generateMindMap(documentId, "english", controller.signal, generationId);
      if (generationVersion.current !== version || controller.signal.aborted) return;
      setNodePositions({}); setSelected(null); pendingFit.current = true;
      setMindMap(generated); setCollapsed(new Set());
      if (initialInstruction) {
        setChatLoading(true);
        try {
          const customized = await customizeMindMap(documentId, generated, initialInstruction);
          if (generationVersion.current !== version || controller.signal.aborted) return;
          setMindMap(customized);
          pendingFit.current = true;
          setNotice("Mind map updated.");
        } catch (customizationError) {
          if (generationVersion.current === version) {
            setError(
              `The mind map was generated, but the instruction could not be applied: ${customizationError instanceof Error
                ? customizationError.message
                : "Please try again."
              }`,
            );
          }
        } finally {
          setChatLoading(false);
        }
      }
    } catch (e) {
      if (generationVersion.current === version) {
        setError(timedOut
          ? "Mind map generation took longer than 15 minutes and was stopped. Please try again."
          : e instanceof Error ? e.message : "Could not generate the map.");
      }
    } finally {
      window.clearTimeout(timeoutId); window.clearInterval(elapsedId);
      controller.abort();
      if (activeGeneration.current?.version === version) activeGeneration.current = null;
      if (generationVersion.current === version) { setLoading(false); setStopping(false); }
    }
  };
  const stopGeneration = async () => {
    const active = activeGeneration.current;
    if (!active) return;
    const stopVersion = generationVersion.current + 1;
    generationVersion.current = stopVersion;
    activeGeneration.current = null;
    const cancellationRequest = cancelMindMapGeneration(active.id);
    active.controller.abort();
    setLoading(false); setStopping(true); setError(""); setNotice("Stopping generation…");
    try {
      await cancellationRequest;
      if (generationVersion.current === stopVersion) setNotice("Generation stopped.");
    } catch {
      if (generationVersion.current === stopVersion) {
        setNotice("The browser request stopped, but the backend could not confirm stopping the active generation.");
      }
    } finally {
      if (generationVersion.current === stopVersion) setStopping(false);
    }
  };
  const sendInstruction = async (text = draft) => {
    const instruction = text.trim();
    if (!instruction || !documentId || !mindMap || chatLoading) return;
    setChatLoading(true); setError(""); setNotice("");
    try {
      const updated = await customizeMindMap(documentId, mindMap, instruction);
      setMindMap(updated); setCollapsed(new Set()); setDraft(""); setNotice("Mind map updated.");
      pendingFit.current = true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update the map. Please retry.");
    } finally { setChatLoading(false); }
  };
  const zoomBy = (factor: number) => {
    const nextZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoom * factor));
    setPan((current) => ({
      x: W / 2 - ((W / 2 - current.x) / zoom) * nextZoom,
      y: H / 2 - ((H / 2 - current.y) / zoom) * nextZoom,
    }));
    setZoom(nextZoom);
  };
  const resetView = () => fitGraph();
  const pointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0 || (e.target as HTMLElement).closest(".mind-map-node")) return;
    const point = toCanvasPoint(e.clientX, e.clientY);
    if (!point) return;
    e.preventDefault();
    canvasDrag.current = { id: e.pointerId, point };
    e.currentTarget.setPointerCapture(e.pointerId);
    setDragging(true);
  };
  const pointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!canvasDrag.current || canvasDrag.current.id !== e.pointerId) return;
    const point = toCanvasPoint(e.clientX, e.clientY);
    if (!point) return;
    const dx = point.x - canvasDrag.current.point.x;
    const dy = point.y - canvasDrag.current.point.y;
    canvasDrag.current = { id: e.pointerId, point };
    setPan((current) => ({ x: current.x + dx, y: current.y + dy }));
  };
  const pointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (canvasDrag.current?.id === e.pointerId) {
      canvasDrag.current = null; setDragging(false);
      if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
    }
  };
  const nodePointerDown = (e: React.PointerEvent<HTMLButtonElement>, node: Node) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    suppressNodeClick.current = null;
    const point = toCanvasPoint(e.clientX, e.clientY);
    if (!point) return;
    nodeDrag.current = {
      id: e.pointerId,
      nodeId: node.id,
      start: point,
      origin: { x: node.x, y: node.y },
      moved: false,
    };
    e.currentTarget.setPointerCapture(e.pointerId);
    setDraggedNodeId(node.id);
  };
  const nodePointerMove = (e: React.PointerEvent<HTMLButtonElement>) => {
    const active = nodeDrag.current;
    if (!active || active.id !== e.pointerId) return;
    const point = toCanvasPoint(e.clientX, e.clientY);
    if (!point) return;
    const dx = (point.x - active.start.x) / zoom;
    const dy = (point.y - active.start.y) / zoom;
    if (Math.hypot(dx, dy) > 3) active.moved = true;
    const size = nodeSize(graph?.byId.get(active.nodeId)?.kind ?? "topic");
    const x = Math.max(size.width / 2, Math.min(W - size.width / 2, active.origin.x + dx));
    const y = Math.max(size.height / 2, Math.min(H - size.height / 2, active.origin.y + dy));
    setNodePositions((current) => ({ ...current, [active.nodeId]: { x, y } }));
  };
  const nodePointerUp = (e: React.PointerEvent<HTMLButtonElement>) => {
    const active = nodeDrag.current;
    if (!active || active.id !== e.pointerId) return;
    if (active.moved) suppressNodeClick.current = active.nodeId;
    nodeDrag.current = null; setDraggedNodeId(null);
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
  };
  const selectNode = (e: React.MouseEvent<HTMLButtonElement>, node: Node) => {
    e.stopPropagation();
    if (suppressNodeClick.current === node.id) { suppressNodeClick.current = null; return; }
    setSelected(node);
    if (node.kind === "topic") setCollapsed((current) => {
      const next = new Set(current);
      next.has(node.id) ? next.delete(node.id) : next.add(node.id);
      return next;
    });
  };

  const submitComposer = () => {
    if (!documentId || uploading || loading || chatLoading) return;
    if (mindMap) void sendInstruction();
    else void generate(draft);
  };

  return (
    <section className="mind-map-section" aria-label="Mind Map workspace">
      <div className="mind-map-shell">
        <main className="mind-map-main">
          {!mindMap && !loading && (
            <p className="mind-map-empty">Upload PDF</p>
          )}

          {loading && (
            <div className="mind-map-progress" role="status" aria-live="polite">
              <span className="mind-map-spinner" aria-hidden="true" />
              <p>{generationStages.find((stage) => stage.id === generationStage)?.label ?? "Generating mind map"}</p>
              {generationStage === "generating_branches" && chunkProgress && (
                <p>Chunks completed: {chunkProgress.completed} / {chunkProgress.total}</p>
              )}
              <p>Elapsed time: {Math.floor(elapsedSeconds / 60)}:{String(elapsedSeconds % 60).padStart(2, "0")}</p>
              <ol className="mind-map-progress-steps">
                {generationStages.map((stage) => {
                  const active = stage.id === generationStage;
                  const complete = seenStages.has(stage.id) && !active;
                  return (
                    <li key={stage.id} className={active ? "is-active" : complete ? "is-complete" : ""}>
                      {stage.label}
                    </li>
                  );
                })}
              </ol>
              <button
                className="mind-map-stop"
                type="button"
                disabled={stopping}
                onClick={() => void stopGeneration()}
              >
                {stopping ? "Stopping…" : "Stop generation"}
              </button>
            </div>
          )}

          {mindMap && graph && (
            <>
              <div
                ref={viewport}
                className={`mind-map-viewport${dragging ? " is-dragging" : ""}`}
                onPointerDown={pointerDown}
                onPointerMove={pointerMove}
                onPointerUp={pointerUp}
                onPointerCancel={pointerUp}
                aria-label="Interactive mind map. Drag a node to move it and drag the background to pan."
              >
                <svg
                  ref={canvas}
                  className="mind-map-canvas"
                  viewBox={`0 0 ${graph.width} ${graph.height}`}
                  role="img"
                  aria-label={`Mind map for ${mindMap.central_topic.label}`}
                >
                  <g className="mind-map-transform" transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
                    {graph.links.map((link, index) => {
                      const from = graph.byId.get(link.from);
                      const to = graph.byId.get(link.to);
                      if (!from || !to) return null;
                      return (
                        <path
                          key={`${link.from}-${link.to}-${index}`}
                          className={`mind-map-link mind-map-link--${link.kind}`}
                          d={edgePath(from, to, index)}
                        />
                      );
                    })}
                    {graph.nodes.map((node) => {
                      const size = nodeSize(node.kind);
                      return (
                        <foreignObject
                          key={node.id}
                          x={node.x - size.width / 2}
                          y={node.y - size.height / 2}
                          width={size.width}
                          height={size.height}
                          className="mind-map-node-wrap"
                        >
                          <button
                            className={`mind-map-node mind-map-node--${node.kind}${selected?.id === node.id ? " is-selected" : ""}${draggedNodeId === node.id ? " is-dragging" : ""}`}
                            onPointerDown={(event) => nodePointerDown(event, node)}
                            onPointerMove={nodePointerMove}
                            onPointerUp={nodePointerUp}
                            onPointerCancel={nodePointerUp}
                            onClick={(event) => selectNode(event, node)}
                          >
                            <span className="mind-map-node__kind">{node.kind}</span>
                            <strong>{node.label}</strong>
                            <span className="mind-map-node__description">{node.description}</span>
                          </button>
                        </foreignObject>
                      );
                    })}
                  </g>
                </svg>
              </div>
              <div className="mind-map-controls" aria-label="Mind map zoom controls">
                <button type="button" onClick={() => zoomBy(1 / 1.25)} aria-label="Zoom out">−</button>
                <span aria-live="polite">{Math.round(zoom * 100)}%</span>
                <button type="button" onClick={() => zoomBy(1.25)} aria-label="Zoom in">+</button>
                <button type="button" className="mind-map-fit" onClick={resetView}>Fit</button>
              </div>
              {selected && (
                <aside className="mind-map-selection" aria-live="polite">
                  <span>{selected.relationship ?? selected.kind}</span>
                  <p>{selected.description}</p>
                </aside>
              )}
            </>
          )}

          {(uploadError || error || notice) && (
            <div className="mind-map-feedback" aria-live="polite">
              {uploadError && <p role="alert">{uploadError}</p>}
              {error && <p role="alert">{error}</p>}
              {notice && <p role="status">{notice}</p>}
            </div>
          )}

          <div className="mind-map-composer">
            <input
              ref={fileInput}
              className="mind-map-file-input"
              type="file"
              accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
              onChange={(event) => {
                void chooseFile(event.target.files?.[0]);
                event.currentTarget.value = "";
              }}
            />
            {filename && (
              <div className="mind-map-file-name" title={filename}>
                <span>{filename}</span>
                {uploading && <span role="status">Uploading…</span>}
              </div>
            )}
            <div className="mind-map-composer__row">
              <button
                className="mind-map-attach"
                type="button"
                onClick={() => fileInput.current?.click()}
                disabled={uploading || loading || chatLoading}
                aria-label="Upload a PDF, TXT, or MD document"
                title="Upload document"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M12 5v14M5 12h14" />
                </svg>
              </button>
              <textarea
                ref={composerTextarea}
                value={draft}
                onChange={(event) => setDraft(event.currentTarget.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                    event.preventDefault();
                    submitComposer();
                  }
                }}
                aria-label="Optional mind map instruction"
                disabled={uploading || loading || chatLoading}
                rows={1}
              />
              <button
                className="mind-map-send"
                type="button"
                onClick={submitComposer}
                disabled={!documentId || uploading || loading || chatLoading || Boolean(mindMap && !draft.trim())}
                aria-label={mindMap ? "Customize mind map" : "Generate mind map"}
                title={mindMap ? "Apply instruction" : "Generate mind map"}
              >
                {chatLoading ? (
                  <span className="mind-map-send__spinner" aria-hidden="true" />
                ) : (
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M12 19V5m-7 7 7-7 7 7" />
                  </svg>
                )}
              </button>
            </div>
          </div>
        </main>
      </div>
    </section>
  );
}
