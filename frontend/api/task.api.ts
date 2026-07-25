import { httpClient } from "./client";
import { TasksResponse, TaskItem, CreateTaskRequest, UpdateTaskRequest } from "./types";

export const taskApi = {
  getProjectTasks: async (projectId: string): Promise<TasksResponse> => {
    return httpClient<TasksResponse>(`/tasks?project_id=${projectId}`);
  },

  createTask: async (taskData: CreateTaskRequest): Promise<TaskItem> => {
    return httpClient<TaskItem>("/tasks", {
      method: "POST",
      body: JSON.stringify(taskData),
    });
  },

  updateTaskStatus: async (taskId: string, status: string): Promise<TaskItem> => {
    return httpClient<TaskItem>(`/tasks/${taskId}`, {
      method: "PUT",
      body: JSON.stringify({ status }),
    });
  },

  updateTaskDetails: async (taskId: string, payload: UpdateTaskRequest): Promise<TaskItem> => {
    return httpClient<TaskItem>(`/tasks/${taskId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },

  getTaskById: async (taskId: string): Promise<TaskItem> => {
    return httpClient<TaskItem>(`/tasks/${taskId}`);
  },
};
