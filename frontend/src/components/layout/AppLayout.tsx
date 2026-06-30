import React from "react";
import { Box, Toolbar, useMediaQuery, useTheme } from "@mui/material";
import Sidebar, { DRAWER_WIDTH } from "./Sidebar";
import TopBar from "./TopBar";
import ActiveJobsBar from "../common/ActiveJobsBar";
import { useAppStore } from "../../store/appStore";
import { useWebSocket } from "../../hooks/useWebSocket";
import { useProjectStore } from "../../store/projectStore";

interface AppLayoutProps {
  children: React.ReactNode;
}

export default function AppLayout({ children }: AppLayoutProps) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const sidebarOpen = useAppStore((s) => s.sidebarOpen);
  const setSidebarOpen = useAppStore((s) => s.setSidebarOpen);
  const currentProject = useProjectStore((s) => s.currentProject);

  // Global WebSocket for the current project
  useWebSocket({
    projectId: currentProject?.id,
    autoReconnect: true,
  });

  return (
    <Box sx={{ display: "flex", minHeight: "100vh", bgcolor: "background.default" }}>
      <TopBar onMenuClick={() => setSidebarOpen(!sidebarOpen)} />

      <Sidebar
        open={isMobile ? sidebarOpen : true}
        onClose={() => setSidebarOpen(false)}
        variant={isMobile ? "temporary" : "permanent"}
      />

      <Box
        component="main"
        sx={{
          flexGrow: 1,
          ml: { sm: `${DRAWER_WIDTH}px` },
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <Toolbar />
        <Box
          sx={{
            flex: 1,
            p: { xs: 2, sm: 3 },
          }}
        >
          {children}
        </Box>
      </Box>

      <ActiveJobsBar />
    </Box>
  );
}
