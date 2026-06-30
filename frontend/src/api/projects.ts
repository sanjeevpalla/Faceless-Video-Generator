import apiClient from "./client";
import { Project } from "../store/projectStore";

export interface CreateProjectPayload {
  name: string;
  description?: string;
  language?: string;
  project_type?: "deep_dive" | "ai_news";
}

export interface UpdateProjectPayload {
  name?: string;
  description?: string;
  status?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface FileUploadStatus {
  file_type: string;
  filename: string;
  size: number;
  status: string;
  message: string;
  path?: string;
}

export const projectsApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    status?: string;
    include_archived?: boolean;
  }): Promise<PaginatedResponse<Project>> => {
    const response = await apiClient.get("/projects", { params });
    return response.data;
  },

  get: async (projectId: string): Promise<Project> => {
    const response = await apiClient.get(`/projects/${projectId}`);
    return response.data;
  },

  create: async (data: CreateProjectPayload): Promise<Project> => {
    const response = await apiClient.post("/projects", data);
    return response.data;
  },

  update: async (projectId: string, data: UpdateProjectPayload): Promise<Project> => {
    const response = await apiClient.patch(`/projects/${projectId}`, data);
    return response.data;
  },

  delete: async (projectId: string, deleteFiles = false): Promise<{ message: string }> => {
    const response = await apiClient.delete(`/projects/${projectId}`, {
      params: { delete_files: deleteFiles },
    });
    return response.data;
  },

  archive: async (projectId: string): Promise<Project> => {
    const response = await apiClient.post(`/projects/${projectId}/archive`);
    return response.data;
  },

  duplicate: async (projectId: string): Promise<Project> => {
    const response = await apiClient.post(`/projects/${projectId}/duplicate`);
    return response.data;
  },

  uploadFile: async (
    projectId: string,
    fileType: string,
    file: File,
    onProgress?: (percent: number) => void
  ): Promise<FileUploadStatus> => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await apiClient.post(
      `/projects/${projectId}/files/${fileType}`,
      formData,
      {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (progressEvent) => {
          if (onProgress && progressEvent.total) {
            const percent = Math.round(
              (progressEvent.loaded * 100) / progressEvent.total
            );
            onProgress(percent);
          }
        },
      }
    );
    return response.data;
  },

  deleteFile: async (projectId: string, fileType: string): Promise<{ message: string }> => {
    const response = await apiClient.delete(`/projects/${projectId}/files/${fileType}`);
    return response.data;
  },

  validate: async (projectId: string): Promise<{
    all_valid: boolean;
    results: Record<string, { valid: boolean; errors: string[]; warnings: string[]; info: Record<string, unknown> }>;
  }> => {
    const response = await apiClient.post(`/projects/${projectId}/validate`);
    return response.data;
  },
};
