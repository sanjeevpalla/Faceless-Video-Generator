import { create } from "zustand";
import { devtools } from "zustand/middleware";

export type NotificationType = "info" | "success" | "warning" | "error";

export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  message?: string;
  timestamp: number;
  read: boolean;
  autoClose?: number;
}

export interface ActiveJob {
  jobId: string;
  projectId: string;
  jobType: string;
  progress: number;
  status: string;
  message?: string;
}

interface AppStore {
  wsConnected: boolean;
  notifications: Notification[];
  sidebarOpen: boolean;
  activeJobs: Record<string, ActiveJob>;
  theme: "dark" | "light";
  singleClickEnabled: boolean;

  // Actions
  setWsConnected: (connected: boolean) => void;
  addNotification: (notification: Omit<Notification, "id" | "timestamp" | "read">) => void;
  markNotificationRead: (id: string) => void;
  clearNotifications: () => void;
  removeNotification: (id: string) => void;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
  setActiveJob: (job: ActiveJob) => void;
  removeActiveJob: (jobId: string) => void;
  updateActiveJob: (jobId: string, update: Partial<ActiveJob>) => void;
  setSingleClickEnabled: (enabled: boolean) => void;
}

let notifCounter = 0;

export const useAppStore = create<AppStore>()(
  devtools(
    (set) => ({
      wsConnected: false,
      notifications: [],
      sidebarOpen: true,
      activeJobs: {},
      theme: "dark",
      singleClickEnabled: false,

      setWsConnected: (connected) => set({ wsConnected: connected }),

      addNotification: (notification) =>
        set((state) => {
          const id = `notif_${Date.now()}_${++notifCounter}`;
          return {
            notifications: [
              {
                ...notification,
                id,
                timestamp: Date.now(),
                read: false,
              },
              ...state.notifications,
            ].slice(0, 50), // keep last 50
          };
        }),

      markNotificationRead: (id) =>
        set((state) => ({
          notifications: state.notifications.map((n) =>
            n.id === id ? { ...n, read: true } : n
          ),
        })),

      clearNotifications: () => set({ notifications: [] }),

      removeNotification: (id) =>
        set((state) => ({
          notifications: state.notifications.filter((n) => n.id !== id),
        })),

      setSidebarOpen: (open) => set({ sidebarOpen: open }),

      toggleSidebar: () =>
        set((state) => ({ sidebarOpen: !state.sidebarOpen })),

      setActiveJob: (job) =>
        set((state) => ({
          activeJobs: { ...state.activeJobs, [job.jobId]: job },
        })),

      removeActiveJob: (jobId) =>
        set((state) => {
          const next = { ...state.activeJobs };
          delete next[jobId];
          return { activeJobs: next };
        }),

      updateActiveJob: (jobId, update) =>
        set((state) => ({
          activeJobs: {
            ...state.activeJobs,
            [jobId]: { ...state.activeJobs[jobId], ...update },
          },
        })),

      setSingleClickEnabled: (enabled) => set({ singleClickEnabled: enabled }),
    }),
    { name: "AppStore" }
  )
);
