import React, { useState } from "react";
import {
  Box,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Typography,
  Divider,
  Chip,
  Avatar,
  CircularProgress,
  Collapse,
} from "@mui/material";
import {
  Dashboard as DashboardIcon,
  FolderOpen as ProjectIcon,
  Image as ImageIcon,
  MovieCreation as ClipsIcon,
  RecordVoiceOver as VoiceIcon,
  Subtitles as SubtitleIcon,
  PhotoCamera as ThumbnailIcon,
  VideoLibrary as VideoIcon,
  Settings as SettingsIcon,
  Videocam as LogoIcon,
  AutoAwesomeMotion as ContentIcon,
  TrendingUp as TrendIcon,
  Search as ResearchIcon,
  Article as ScriptIcon,
  ViewDay as ScenesIcon,
  Tag as SeoIcon,
  CheckCircle as DoneIcon,
  ErrorOutline as ErrorIcon,
  ExpandMore as ExpandMoreIcon,
  ChevronRight as ChevronRightIcon,
} from "@mui/icons-material";
import { useNavigate, useLocation } from "react-router-dom";
import { useProjectStore } from "../../store";

const DRAWER_WIDTH = 240;

interface NavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
  requiresProject?: boolean;
  hideForAiNews?: boolean;
  aiNewsOnly?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", path: "/", icon: <DashboardIcon /> },
  { label: "Project", path: "/project", icon: <ProjectIcon />, requiresProject: true },
  { label: "Content", path: "/content", icon: <ContentIcon />, requiresProject: true },
  { label: "Images", path: "/images", icon: <ImageIcon />, requiresProject: true },
  { label: "Voice", path: "/voice", icon: <VoiceIcon />, requiresProject: true },
  { label: "Subtitles", path: "/subtitles", icon: <SubtitleIcon />, requiresProject: true },
  { label: "Clips", path: "/clips", icon: <ClipsIcon />, requiresProject: true, hideForAiNews: true },
  { label: "Clips", path: "/ai-news-clips", icon: <ClipsIcon />, requiresProject: true, aiNewsOnly: true },
  { label: "Thumbnail", path: "/thumbnail", icon: <ThumbnailIcon />, requiresProject: true },
  { label: "Video", path: "/video", icon: <VideoIcon />, requiresProject: true },
];

const CONTENT_STEPS = [
  { key: "trends",       label: "Trend Discovery", aiNewsLabel: "AI News Topics", icon: <TrendIcon fontSize="small" /> },
  { key: "research",     label: "Research",         aiNewsLabel: null,             icon: <ResearchIcon fontSize="small" /> },
  { key: "script",       label: "Script",           aiNewsLabel: "Script",         icon: <ScriptIcon fontSize="small" /> },
  { key: "scenes",       label: "Scenes JSON",      aiNewsLabel: "Scenes JSON",    icon: <ScenesIcon fontSize="small" /> },
  { key: "imagePrompts", label: "Image Prompts",    aiNewsLabel: "Image Prompts",  icon: <ImageIcon fontSize="small" /> },
  { key: "thumbnail",    label: "Thumbnail",        aiNewsLabel: "Thumbnail",      icon: <ThumbnailIcon fontSize="small" /> },
  { key: "seo",          label: "SEO Metadata",     aiNewsLabel: "SEO Metadata",   icon: <SeoIcon fontSize="small" /> },
] as const;

const STATUS_COLORS: Record<string, string> = {
  created: "#9090A8",
  processing: "#FFB300",
  completed: "#00E676",
  failed: "#FF5252",
  archived: "#505068",
};

interface SidebarProps {
  open: boolean;
  onClose: () => void;
  variant?: "permanent" | "temporary";
}

export default function Sidebar({ open, onClose, variant = "permanent" }: SidebarProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const currentProject = useProjectStore((s) => s.currentProject);
  const cs = useProjectStore((s) => s.contentGenState);

  const isAiNews = currentProject?.project_type === "ai_news";
  const isContentSection = location.pathname.startsWith("/content");
  const [contentExpanded, setContentExpanded] = useState(isContentSection);

  const handleNav = (path: string) => {
    navigate(path);
    if (variant === "temporary") onClose();
  };

  function stepIcon(key: string, defaultIcon: React.ReactNode) {
    const state = (cs as Record<string, any>)[key];
    const status = state?.status ?? "idle";
    if (status === "running") return <CircularProgress size={14} />;
    if (status === "done")    return <DoneIcon fontSize="small" sx={{ color: "success.main" }} />;
    if (status === "error")   return <ErrorIcon fontSize="small" sx={{ color: "error.main" }} />;
    return defaultIcon;
  }

  const drawerContent = (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Logo */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1.5,
          px: 2.5,
          py: 2,
          borderBottom: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        <Avatar sx={{ bgcolor: "primary.main", width: 36, height: 36 }}>
          <LogoIcon fontSize="small" />
        </Avatar>
        <Box>
          <Typography variant="subtitle2" fontWeight={700} lineHeight={1.2}>
            Faceless
          </Typography>
          <Typography variant="caption" color="text.secondary" lineHeight={1}>
            Video Generator
          </Typography>
        </Box>
      </Box>

      {/* Current Project */}
      {currentProject && (
        <Box
          sx={{
            mx: 2,
            mt: 2,
            mb: 1,
            p: 1.5,
            bgcolor: "rgba(108,99,255,0.08)",
            border: "1px solid rgba(108,99,255,0.2)",
            borderRadius: 2,
          }}
        >
          <Typography variant="caption" color="primary.light" fontWeight={600} display="block">
            ACTIVE PROJECT
          </Typography>
          <Typography
            variant="body2"
            fontWeight={600}
            noWrap
            title={currentProject.name}
            sx={{ mt: 0.3 }}
          >
            {currentProject.name}
          </Typography>
          <Chip
            label={currentProject.status.toUpperCase()}
            size="small"
            sx={{
              mt: 0.5,
              height: 18,
              fontSize: "0.65rem",
              bgcolor: `${STATUS_COLORS[currentProject.status] || "#9090A8"}22`,
              color: STATUS_COLORS[currentProject.status] || "#9090A8",
            }}
          />
        </Box>
      )}

      {/* Main Nav */}
      <Box sx={{ px: 1.5, pt: 1, flex: 1, overflowY: "auto" }}>
        <List dense disablePadding>
          {NAV_ITEMS.filter((item) => {
            if (item.hideForAiNews && isAiNews) return false;
            if (item.aiNewsOnly && !isAiNews) return false;
            return true;
          }).map((item) => {
            const isContent = item.path === "/content";
            const isActive = isContent ? isContentSection : location.pathname === item.path;
            const isDisabled = item.requiresProject && !currentProject;

            return (
              <React.Fragment key={item.path}>
                <ListItem disablePadding sx={{ mb: 0.25 }}>
                  <ListItemButton
                    selected={isActive}
                    disabled={isDisabled}
                    onClick={() => {
                      if (isContent) {
                        setContentExpanded((prev) => !prev);
                      } else {
                        handleNav(item.path);
                      }
                    }}
                    sx={{ py: 1, px: 1.5 }}
                  >
                    <ListItemIcon
                      sx={{
                        minWidth: 36,
                        color: isActive ? "primary.main" : "text.secondary",
                      }}
                    >
                      {item.icon}
                    </ListItemIcon>
                    <ListItemText
                      primary={item.label}
                      primaryTypographyProps={{
                        variant: "body2",
                        fontWeight: isActive ? 600 : 400,
                        color: isActive ? "primary.light" : "text.primary",
                      }}
                    />
                    {isContent && currentProject && (
                      contentExpanded
                        ? <ExpandMoreIcon fontSize="small" sx={{ color: "text.disabled" }} />
                        : <ChevronRightIcon fontSize="small" sx={{ color: "text.disabled" }} />
                    )}
                  </ListItemButton>
                </ListItem>

                {/* Content sub-steps — Research hidden for AI News */}
                {isContent && currentProject && (
                  <Collapse in={contentExpanded} unmountOnExit>
                    <List dense disablePadding>
                      {CONTENT_STEPS
                        .filter((s) => !(isAiNews && s.aiNewsLabel === null))
                        .map((s) => {
                          const stepPath = `/content/${s.key}`;
                          const isStepActive = location.pathname === stepPath;
                          const label = isAiNews && s.aiNewsLabel ? s.aiNewsLabel : s.label;
                          return (
                            <ListItem key={s.key} disablePadding>
                              <ListItemButton
                                selected={isStepActive}
                                onClick={() => handleNav(stepPath)}
                                sx={{ py: 0.7, pl: 4.5, pr: 1.5, minHeight: 36 }}
                              >
                                <ListItemIcon
                                  sx={{
                                    minWidth: 28,
                                    color: isStepActive ? "primary.main" : "text.disabled",
                                  }}
                                >
                                  {stepIcon(s.key, s.icon)}
                                </ListItemIcon>
                                <ListItemText
                                  primary={label}
                                  primaryTypographyProps={{
                                    variant: "caption",
                                    fontWeight: isStepActive ? 700 : 400,
                                    color: isStepActive ? "primary.light" : "text.secondary",
                                    fontSize: "0.75rem",
                                  }}
                                />
                              </ListItemButton>
                            </ListItem>
                          );
                        })}
                    </List>
                  </Collapse>
                )}
              </React.Fragment>
            );
          })}
        </List>
      </Box>

      <Divider sx={{ borderColor: "rgba(255,255,255,0.06)" }} />

      {/* Settings */}
      <Box sx={{ px: 1.5, py: 1 }}>
        <ListItem disablePadding>
          <ListItemButton
            selected={location.pathname === "/settings"}
            onClick={() => handleNav("/settings")}
            sx={{ py: 1, px: 1.5 }}
          >
            <ListItemIcon
              sx={{
                minWidth: 36,
                color: location.pathname === "/settings" ? "primary.main" : "text.secondary",
              }}
            >
              <SettingsIcon />
            </ListItemIcon>
            <ListItemText
              primary="Settings"
              primaryTypographyProps={{ variant: "body2" }}
            />
          </ListItemButton>
        </ListItem>
      </Box>
    </Box>
  );

  return (
    <Drawer
      variant={variant}
      open={open}
      onClose={onClose}
      sx={{
        width: DRAWER_WIDTH,
        flexShrink: 0,
        "& .MuiDrawer-paper": {
          width: DRAWER_WIDTH,
          boxSizing: "border-box",
        },
      }}
    >
      {drawerContent}
    </Drawer>
  );
}

export { DRAWER_WIDTH };
