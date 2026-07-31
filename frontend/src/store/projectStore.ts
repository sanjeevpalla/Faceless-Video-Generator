import { create } from "zustand";
import { devtools, persist, createJSONStorage } from "zustand/middleware";

export interface StepProgress {
  status: "pending" | "running" | "completed" | "failed" | "paused";
  progress: number;
  total: number;
  completed: number;
  error?: string;
}

export interface ProgressState {
  images: StepProgress;
  voice: StepProgress;
  subtitles: StepProgress;
  thumbnail: StepProgress;
  video: StepProgress;
  metadata: StepProgress;
  translate?: StepProgress;
  wan2: StepProgress;
  blog: StepProgress;
}

export interface FileStatusDetail {
  status: "missing" | "ready" | "processing" | "failed";
  filename: string | null;
  path: string | null;
  size: number | null;
}

export interface Project {
  id: string;
  name: string;
  status: string;
  description?: string;
  language?: string;
  languages?: string[];
  language_voices?: Record<string, string>;
  project_type?: "deep_dive" | "ai_news";
  created_at: string;
  updated_at: string;
  project_dir?: string;
  input_files_status: Record<string, FileStatusDetail>;
  progress_state: ProgressState;
  language_progress?: Record<string, Record<string, unknown>>;
  resume_state: Record<string, unknown>;
}

export interface PipelineStepState {
  stepName: string;
  stepLabel: string;
  stepIndex: number;
  totalSteps: number;
}

export interface TrendCandidate {
  id: string;
  title: string;
  summary: string;
}

export interface AwaitingWhatsAppState {
  candidateTopics: TrendCandidate[];
  whatsappMessageId: string;
}

export interface PipelineRunState {
  status: "idle" | "running" | "awaiting_input" | "completed" | "failed";
  progress: number;
  currentStep: PipelineStepState | null;
  error?: string;
  jobId?: string;
  awaitingWhatsapp: AwaitingWhatsAppState | null;
}

const defaultPipelineState = (): PipelineRunState => ({
  status: "idle",
  progress: 0,
  currentStep: null,
  awaitingWhatsapp: null,
});

export interface ContentStepState {
  status: "idle" | "running" | "done" | "error";
  content: string;
  error?: string;
}

export interface ContentGenState {
  topic: string;
  trends: ContentStepState;
  research: ContentStepState;
  script: ContentStepState;
  scenes: ContentStepState;
  imagePrompts: ContentStepState;
  thumbnail: ContentStepState;
  seo: ContentStepState;
}

const defaultContentState = (): ContentGenState => ({
  topic: "",
  trends:       { status: "idle", content: "" },
  research:     { status: "idle", content: "" },
  script:       { status: "idle", content: "" },
  scenes:       { status: "idle", content: "" },
  imagePrompts: { status: "idle", content: "" },
  thumbnail:    { status: "idle", content: "" },
  seo:          { status: "idle", content: "" },
});

/** Per-language content state, keyed by language code (e.g. "en", "te", "hi"). */
export type ContentGenStateByLang = Record<string, ContentGenState>;

const defaultStep = (): StepProgress => ({
  status: "pending",
  progress: 0,
  total: 0,
  completed: 0,
});

const defaultProgressState = (): ProgressState => ({
  images: defaultStep(),
  voice: defaultStep(),
  subtitles: defaultStep(),
  thumbnail: defaultStep(),
  video: defaultStep(),
  metadata: defaultStep(),
  wan2: defaultStep(),
  blog: defaultStep(),
});

interface ProjectStore {
  currentProject: Project | null;
  projects: Project[];
  selectedSceneId: number | null;
  generationProgress: ProgressState;
  /** Mirror of contentGenStateByLang[activeContentLanguage] — kept in sync by every
   * setter below. Read this when you don't care which language is active (e.g. Sidebar
   * step-status icons); read contentGenStateByLang directly for per-language tabs. */
  contentGenState: ContentGenState;
  contentGenStateByLang: ContentGenStateByLang;
  activeContentLanguage: string;

  /** Pipeline orchestration state (single-click generation). */
  pipelineState: PipelineRunState;

  /** Scene IDs marked for LTX-Video clip generation (empty = not yet initialised = all LTX). */
  ltxSceneIds: Set<number>;

  // Actions
  setCurrentProject: (project: Project | null) => void;
  setProjects: (projects: Project[]) => void;
  updateProgress: (step: keyof ProgressState, data: Partial<StepProgress>) => void;
  setSelectedSceneId: (id: number | null) => void;
  updateProjectInList: (project: Project) => void;
  clearCurrentProject: () => void;
  setLtxSceneIds: (ids: Set<number>) => void;
  toggleLtxSceneId: (id: number) => void;
  updateContentState: (patch: Partial<ContentGenState>, language?: string) => void;
  resetContentState: () => void;
  setActiveContentLanguage: (language: string) => void;
  updatePipelineState: (patch: Partial<PipelineRunState>) => void;
  resetPipelineState: () => void;
}

export const useProjectStore = create<ProjectStore>()(
  devtools(
    persist(
      (set) => ({
        currentProject: null,
        projects: [],
        selectedSceneId: null,
        generationProgress: defaultProgressState(),
        contentGenState: defaultContentState(),
        contentGenStateByLang: {},
        activeContentLanguage: "en",
        pipelineState: defaultPipelineState(),
        ltxSceneIds: new Set<number>(),

        setCurrentProject: (project) =>
          set((state) => {
            const projectChanged = state.currentProject?.id !== project?.id;
            const activeContentLanguage = project?.language || "en";
            const contentGenStateByLang = projectChanged ? {} : state.contentGenStateByLang;
            return {
              currentProject: project,
              ltxSceneIds: projectChanged ? new Set<number>() : state.ltxSceneIds,
              // Reset content state when switching projects
              activeContentLanguage,
              contentGenStateByLang,
              contentGenState: projectChanged
                ? defaultContentState()
                : contentGenStateByLang[activeContentLanguage] ?? defaultContentState(),
              generationProgress: project
                ? (project.progress_state as ProgressState) ?? defaultProgressState()
                : defaultProgressState(),
            };
          }),

      setProjects: (projects) => set({ projects }),

      updateProgress: (step, data) =>
        set((state) => ({
          generationProgress: {
            ...state.generationProgress,
            [step]: {
              ...state.generationProgress[step],
              ...data,
            },
          },
        })),

      setSelectedSceneId: (id) => set({ selectedSceneId: id }),

      updateProjectInList: (project) =>
        set((state) => ({
          projects: state.projects.map((p) =>
            p.id === project.id ? project : p
          ),
          currentProject:
            state.currentProject?.id === project.id
              ? project
              : state.currentProject,
        })),

      clearCurrentProject: () =>
        set({
          currentProject: null,
          selectedSceneId: null,
          ltxSceneIds: new Set<number>(),
          generationProgress: defaultProgressState(),
          contentGenState: defaultContentState(),
          contentGenStateByLang: {},
          activeContentLanguage: "en",
        }),

      updateContentState: (patch, language) =>
        set((state) => {
          const lang = language ?? state.activeContentLanguage;
          const nextForLang = {
            ...(state.contentGenStateByLang[lang] ?? defaultContentState()),
            ...patch,
          };
          const contentGenStateByLang = { ...state.contentGenStateByLang, [lang]: nextForLang };
          return {
            contentGenStateByLang,
            contentGenState: lang === state.activeContentLanguage ? nextForLang : state.contentGenState,
          };
        }),

      resetContentState: () =>
        set((state) => ({
          contentGenState: defaultContentState(),
          contentGenStateByLang: { ...state.contentGenStateByLang, [state.activeContentLanguage]: defaultContentState() },
        })),

      setActiveContentLanguage: (language) =>
        set((state) => ({
          activeContentLanguage: language,
          contentGenState: state.contentGenStateByLang[language] ?? defaultContentState(),
        })),

      updatePipelineState: (patch) =>
        set((state) => ({ pipelineState: { ...state.pipelineState, ...patch } })),

      resetPipelineState: () => set({ pipelineState: defaultPipelineState() }),

      setLtxSceneIds: (ids) => set({ ltxSceneIds: ids }),

      toggleLtxSceneId: (id) =>
        set((state) => {
          const next = new Set(state.ltxSceneIds);
          next.has(id) ? next.delete(id) : next.add(id);
          return { ltxSceneIds: next };
        }),
      }),
      {
        name: "faceless-content-state",
        storage: createJSONStorage(() => localStorage),
        partialize: (state) => ({
          contentGenState: state.contentGenState,
          contentGenStateByLang: state.contentGenStateByLang,
          activeContentLanguage: state.activeContentLanguage,
        }),
      }
    ),
    { name: "ProjectStore" }
  )
);
