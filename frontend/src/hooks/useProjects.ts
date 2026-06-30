import {
  useQuery,
  useMutation,
  useQueryClient,
  UseQueryResult,
} from "@tanstack/react-query";
import { projectsApi, CreateProjectPayload, UpdateProjectPayload } from "../api/projects";
import { Project } from "../store/projectStore";
import { useProjectStore } from "../store";

export const PROJECT_KEYS = {
  all: ["projects"] as const,
  lists: () => [...PROJECT_KEYS.all, "list"] as const,
  list: (params: object) => [...PROJECT_KEYS.lists(), params] as const,
  details: () => [...PROJECT_KEYS.all, "detail"] as const,
  detail: (id: string) => [...PROJECT_KEYS.details(), id] as const,
};

export function useProjects(params?: {
  page?: number;
  page_size?: number;
  status?: string;
  include_archived?: boolean;
}) {
  return useQuery({
    queryKey: PROJECT_KEYS.list(params || {}),
    queryFn: () => projectsApi.list(params),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}

export function useProject(projectId: string | null | undefined) {
  return useQuery({
    queryKey: PROJECT_KEYS.detail(projectId!),
    queryFn: () => projectsApi.get(projectId!),
    enabled: !!projectId,
    staleTime: 10_000,
  }) as UseQueryResult<Project>;
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  const setCurrentProject = useProjectStore((s) => s.setCurrentProject);

  return useMutation({
    mutationFn: (data: CreateProjectPayload) => projectsApi.create(data),
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: PROJECT_KEYS.lists() });
      queryClient.setQueryData(PROJECT_KEYS.detail(project.id), project);
      setCurrentProject(project);
    },
  });
}

export function useUpdateProject() {
  const queryClient = useQueryClient();
  const updateInList = useProjectStore((s) => s.updateProjectInList);

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateProjectPayload }) =>
      projectsApi.update(id, data),
    onSuccess: (project) => {
      queryClient.setQueryData(PROJECT_KEYS.detail(project.id), project);
      queryClient.invalidateQueries({ queryKey: PROJECT_KEYS.lists() });
      updateInList(project);
    },
  });
}

export function useDeleteProject() {
  const queryClient = useQueryClient();
  const clearCurrentProject = useProjectStore((s) => s.clearCurrentProject);
  const currentProject = useProjectStore((s) => s.currentProject);

  return useMutation({
    mutationFn: ({ id, deleteFiles }: { id: string; deleteFiles?: boolean }) =>
      projectsApi.delete(id, deleteFiles),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: PROJECT_KEYS.lists() });
      queryClient.removeQueries({ queryKey: PROJECT_KEYS.detail(variables.id) });
      if (currentProject?.id === variables.id) {
        clearCurrentProject();
      }
    },
  });
}

export function useArchiveProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (projectId: string) => projectsApi.archive(projectId),
    onSuccess: (project) => {
      queryClient.setQueryData(PROJECT_KEYS.detail(project.id), project);
      queryClient.invalidateQueries({ queryKey: PROJECT_KEYS.lists() });
    },
  });
}

export function useDuplicateProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (projectId: string) => projectsApi.duplicate(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: PROJECT_KEYS.lists() });
    },
  });
}

export function useUploadFile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      projectId,
      fileType,
      file,
      onProgress,
    }: {
      projectId: string;
      fileType: string;
      file: File;
      onProgress?: (percent: number) => void;
    }) => projectsApi.uploadFile(projectId, fileType, file, onProgress),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: PROJECT_KEYS.detail(variables.projectId),
      });
    },
  });
}
