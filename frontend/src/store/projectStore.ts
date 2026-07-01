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
  project_type?: "deep_dive" | "ai_news";
  created_at: string;
  updated_at: string;
  project_dir?: string;
  input_files_status: Record<string, FileStatusDetail>;
  progress_state: ProgressState;
  resume_state: Record<string, unknown>;
}

export interface PipelineStepState {
  stepName: string;
  stepLabel: string;
  stepIndex: number;
  totalSteps: number;
}

export interface PipelineRunState {
  status: "idle" | "running" | "completed" | "failed";
  progress: number;
  currentStep: PipelineStepState | null;
  error?: string;
  jobId?: string;
}

const defaultPipelineState = (): PipelineRunState => ({
  status: "idle",
  progress: 0,
  currentStep: null,
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
});

interface ProjectStore {
  currentProject: Project | null;
  projects: Project[];
  selectedSceneId: number | null;
  generationProgress: ProgressState;
  contentGenState: ContentGenState;

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
  updateContentState: (patch: Partial<ContentGenState>) => void;
  resetContentState: () => void;
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
        pipelineState: defaultPipelineState(),
        ltxSceneIds: new Set<number>(),

        setCurrentProject: (project) =>
          set((state) => ({
            currentProject: project,
            ltxSceneIds: state.currentProject?.id !== project?.id ? new Set<number>() : state.ltxSceneIds,
            // Reset content state when switching projects
            contentGenState: state.currentProject?.id !== project?.id ? defaultContentState() : state.contentGenState,
            generationProgress: project
              ? (project.progress_state as ProgressState) ?? defaultProgressState()
              : defaultProgressState(),
          })),

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
        }),

      updateContentState: (patch) =>
        set((state) => ({
          contentGenState: { ...state.contentGenState, ...patch },
        })),

      resetContentState: () => set({ contentGenState: defaultContentState() }),

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
        partialize: (state) => ({ contentGenState: state.contentGenState }),
      }
    ),
    { name: "ProjectStore" }
  )
);
