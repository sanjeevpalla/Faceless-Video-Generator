import React, { useState } from "react";
import {
  AppBar,
  Toolbar,
  Typography,
  IconButton,
  Chip,
  Box,
  Badge,
  Menu,
  MenuItem,
  ListItemText,
  Divider,
  Tooltip,
} from "@mui/material";
import {
  Menu as MenuIcon,
  Circle as CircleIcon,
  Notifications as NotificationsIcon,
  CheckCircle as CheckCircleIcon,
} from "@mui/icons-material";
import { useAppStore } from "../../store/appStore";
import { useProjectStore } from "../../store/projectStore";

interface TopBarProps {
  onMenuClick: () => void;
}

export default function TopBar({ onMenuClick }: TopBarProps) {
  const wsConnected = useAppStore((s) => s.wsConnected);
  const notifications = useAppStore((s) => s.notifications);
  const clearNotifications = useAppStore((s) => s.clearNotifications);
  const markRead = useAppStore((s) => s.markNotificationRead);
  const currentProject = useProjectStore((s) => s.currentProject);

  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const unreadCount = notifications.filter((n) => !n.read).length;

  const handleNotifOpen = (e: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(e.currentTarget);
    notifications.forEach((n) => markRead(n.id));
  };

  const NOTIF_COLORS = {
    info: "#29B6F6",
    success: "#00E676",
    warning: "#FFB300",
    error: "#FF5252",
  };

  return (
    <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}>
      <Toolbar sx={{ gap: 1 }}>
        <IconButton
          edge="start"
          onClick={onMenuClick}
          sx={{ display: { sm: "none" }, color: "text.secondary" }}
        >
          <MenuIcon />
        </IconButton>

        {/* Project Name */}
        <Box sx={{ flex: 1 }}>
          {currentProject ? (
            <Box>
              <Typography variant="h6" fontWeight={700} lineHeight={1.2}>
                {currentProject.name}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Project · {currentProject.id.slice(0, 8)}
              </Typography>
            </Box>
          ) : (
            <Typography variant="h6" fontWeight={700}>
              Faceless Video Generator
            </Typography>
          )}
        </Box>

        {/* WS Status */}
        <Tooltip title={wsConnected ? "Backend connected" : "Backend disconnected"}>
          <Chip
            icon={
              <CircleIcon
                sx={{
                  fontSize: "10px !important",
                  color: wsConnected ? "success.main" : "error.main",
                }}
              />
            }
            label={wsConnected ? "Connected" : "Offline"}
            size="small"
            sx={{
              bgcolor: wsConnected
                ? "rgba(0,230,118,0.1)"
                : "rgba(255,82,82,0.1)",
              color: wsConnected ? "success.main" : "error.main",
              border: `1px solid ${wsConnected ? "rgba(0,230,118,0.3)" : "rgba(255,82,82,0.3)"}`,
              height: 26,
              fontSize: "0.7rem",
            }}
          />
        </Tooltip>

        {/* Notifications */}
        <Tooltip title="Notifications">
          <IconButton onClick={handleNotifOpen} sx={{ color: "text.secondary" }}>
            <Badge badgeContent={unreadCount} color="error" max={9}>
              <NotificationsIcon />
            </Badge>
          </IconButton>
        </Tooltip>

        <Menu
          anchorEl={anchorEl}
          open={Boolean(anchorEl)}
          onClose={() => setAnchorEl(null)}
          PaperProps={{
            sx: {
              width: 320,
              maxHeight: 400,
              mt: 1,
              bgcolor: "#1A1A2E",
              border: "1px solid rgba(255,255,255,0.08)",
            },
          }}
          transformOrigin={{ horizontal: "right", vertical: "top" }}
          anchorOrigin={{ horizontal: "right", vertical: "bottom" }}
        >
          <Box sx={{ px: 2, py: 1, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <Typography variant="subtitle2" fontWeight={700}>
              Notifications
            </Typography>
            {notifications.length > 0 && (
              <Typography
                variant="caption"
                color="primary"
                sx={{ cursor: "pointer" }}
                onClick={clearNotifications}
              >
                Clear all
              </Typography>
            )}
          </Box>
          <Divider sx={{ borderColor: "rgba(255,255,255,0.06)" }} />
          {notifications.length === 0 ? (
            <Box sx={{ py: 3, textAlign: "center" }}>
              <CheckCircleIcon sx={{ color: "text.disabled", mb: 1 }} />
              <Typography variant="body2" color="text.secondary">
                No notifications
              </Typography>
            </Box>
          ) : (
            notifications.slice(0, 20).map((n) => (
              <MenuItem key={n.id} sx={{ alignItems: "flex-start", py: 1.5 }}>
                <CircleIcon
                  sx={{
                    fontSize: 8,
                    mt: 0.8,
                    mr: 1.5,
                    color: NOTIF_COLORS[n.type] || "text.secondary",
                    flexShrink: 0,
                  }}
                />
                <ListItemText
                  primary={n.title}
                  secondary={n.message}
                  primaryTypographyProps={{ variant: "body2", fontWeight: 600 }}
                  secondaryTypographyProps={{ variant: "caption", color: "text.secondary" }}
                />
              </MenuItem>
            ))
          )}
        </Menu>
      </Toolbar>
    </AppBar>
  );
}
