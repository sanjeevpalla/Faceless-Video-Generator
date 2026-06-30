import React, { useState, useEffect } from "react";
import {
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  CircularProgress,
  Skeleton,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from "@mui/material";
import {
  Add as AddIcon,
  FolderOpen as OpenIcon,
  VideoLibrary as VideoIcon,
  CheckCircle as CompletedIcon,
  Work as ActiveIcon,
  Image as ImageIcon,
  Movie as ClipsIcon,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { useProjects, useCreateProject, useDeleteProject, useArchiveProject, useDuplicateProject } from "../hooks/useProjects";
import { useProjectStore } from "../store";
import ProjectCard from "../components/project/ProjectCard";
import ProjectRenameDialog from "../components/project/ProjectRenameDialog";
import { Project } from "../store/projectStore";
import { imagesApi } from "../api/images";
import { voiceApi } from "../api/voice";
import { wan2Api } from "../api/wan2";
import { subtitlesApi } from "../api/subtitles";
import { thumbnailApi } from "../api/thumbnail";
import { videoApi } from "../api/video";

function StatCard({
  title,
  value,
  icon,
  color,
}: {
  title: string;
  value: number | string;
  icon: React.ReactNode;
  color: string;
}) {
  return (
    <Card>
      <CardContent sx={{ p: 2.5 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <Box>
            <Typography variant="caption" color="text.secondary" fontWeight={600} textTransform="uppercase" letterSpacing={1}>
              {title}
            </Typography>
            <Typography variant="h3" fontWeight={800} sx={{ mt: 0.5, color }}>
              {value}
            </Typography>
          </Box>
          <Box
            sx={{
              width: 52,
              height: 52,
              borderRadius: 2,
              bgcolor: `${color}18`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color,
            }}
          >
            {icon}
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [createOpen, setCreateOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDesc, setNewProjectDesc] = useState("");
  const [newProjectLang, setNewProjectLang] = useState("en");
  const [newProjectType, setNewProjectType] = useState<"deep_dive" | "ai_news">("deep_dive");
  const [createNameError, setCreateNameError] = useState("");

  const { data: projectsData, isLoading } = useProjects({ page: 1, page_size: 50 });
  const createProject = useCreateProject();
  const deleteProject = useDeleteProject();
  const archiveProject = useArchiveProject();
  const duplicateProject = useDuplicateProject();
  const setCurrentProject = useProjectStore((s) => s.setCurrentProject);
  const [renameTarget, setRenameTarget] = useState<Project | null>(null);

  const [progressOverrides, setProgressOverrides] = useState<Record<string, Record<string, any>>>({});

  const projects = projectsData?.items || [];
  const totalProjects = projectsData?.total || 0;
  const recentProjects = [...projects]
    .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
    .slice(0, 6);

  const getEffectiveStep = (project: Project, key: string) =>
    progressOverrides[project.id]?.[key] ?? (project.progress_state as any)?.[key];

  const completedCount = projects.filter((p) => {
    const video = getEffectiveStep(p, "video");
    return video?.status === "completed" || p.status === "completed";
  }).length;

  const imagesReadyCount = projects.filter((p) => {
    const img = getEffectiveStep(p, "images");
    return img?.status === "completed";
  }).length;

  const clipsReadyCount = projects.filter((p) => {
    const clips = getEffectiveStep(p, "wan2");
    return clips?.status === "completed";
  }).length;

  const activeCount = projects.filter((p) => p.status === "processing").length;

  const projectIdKey = recentProjects.map((p) => p.id).join(",");
  useEffect(() => {
    if (recentProjects.length === 0) return;
    recentProjects.forEach((project) => {
      const id = project.id;
      const updates: Record<string, any> = {};
      Promise.allSettled([
        imagesApi.listForProject(id).then((r) => {
          if (r.total > 0)
            updates.images = {
              status: r.generated === r.total ? "completed" : "pending",
              progress: r.generated === r.total ? 100 : Math.round((r.generated / r.total) * 100),
              completed: r.generated,
              total: r.total,
            };
        }),
        voiceApi.listForProject(id).then((r) => {
          if (r.total > 0)
            updates.voice = {
              status: r.merged !== null ? "completed" : "pending",
              progress: r.merged !== null ? 100 : Math.round((r.generated / r.total) * 100),
              completed: r.generated,
              total: r.total,
            };
        }),
        wan2Api.listForProject(id).then((r) => {
          if (r.total > 0)
            updates.wan2 = {
              status: r.animated === r.total ? "completed" : "pending",
              progress: r.animated === r.total ? 100 : Math.round((r.animated / r.total) * 100),
              completed: r.animated,
              total: r.total,
            };
        }),
        subtitlesApi.getStatus(id).then((r) => {
          updates.subtitles = {
            status: r.status === "ready" ? "completed" : "pending",
            progress: r.status === "ready" ? 100 : 0,
          };
        }),
        thumbnailApi.getStatus(id).then((r) => {
          updates.thumbnail = {
            status: r.status === "ready" ? "completed" : "pending",
            progress: r.status === "ready" ? 100 : 0,
          };
        }),
        videoApi.getStatus(id).then((r) => {
          if (r.status === "ready") {
            updates.video = { status: "completed", progress: 100 };
            updates.metadata = { status: "completed", progress: 100 };
          }
        }),
      ]).then(() => {
        if (Object.keys(updates).length > 0)
          setProgressOverrides((prev) => ({ ...prev, [id]: { ...prev[id], ...updates } }));
      });
    });
  }, [projectIdKey]);

  const handleCreateProject = async () => {
    if (!newProjectName.trim()) return;
    setCreateNameError("");
    try {
      await createProject.mutateAsync({
        name: newProjectName.trim(),
        description: newProjectDesc.trim() || undefined,
        language: newProjectLang,
        project_type: newProjectType,
      });
      setCreateOpen(false);
      setNewProjectName("");
      setNewProjectDesc("");
      setNewProjectLang("en");
      setNewProjectType("deep_dive");
      setCreateNameError("");
      navigate("/project");
    } catch (err: any) {
      if (err?.status === 409) {
        setCreateNameError(err.message);
      } else {
        console.error("Failed to create project:", err);
      }
    }
  };

  const handleOpen = (project: Project) => {
    setCurrentProject(project);
    navigate("/project");
  };

  const handleDelete = async (project: Project) => {
    if (window.confirm(`Delete project "${project.name}"?`)) {
      await deleteProject.mutateAsync({ id: project.id });
    }
  };

  const handleArchive = async (project: Project) => {
    await archiveProject.mutateAsync(project.id);
  };

  const handleDuplicate = async (project: Project) => {
    await duplicateProject.mutateAsync(project.id);
  };

  const handleRename = (project: Project) => {
    setRenameTarget(project);
  };

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" fontWeight={800} gutterBottom>
          Dashboard
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Manage your faceless video projects
        </Typography>
      </Box>

      {/* Stats */}
      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={6} sm={3}>
          <StatCard
            title="Total Projects"
            value={isLoading ? "—" : totalProjects}
            icon={<VideoIcon />}
            color="#6C63FF"
          />
        </Grid>
        <Grid item xs={6} sm={3}>
          <StatCard
            title="Videos Generated"
            value={isLoading ? "—" : completedCount}
            icon={<CompletedIcon />}
            color="#00E676"
          />
        </Grid>
        <Grid item xs={6} sm={3}>
          <StatCard
            title="Images Ready"
            value={isLoading ? "—" : imagesReadyCount}
            icon={<ImageIcon />}
            color="#29B6F6"
          />
        </Grid>
        <Grid item xs={6} sm={3}>
          <StatCard
            title="Clips Animated"
            value={isLoading ? "—" : clipsReadyCount}
            icon={<ClipsIcon />}
            color="#FFB300"
          />
        </Grid>
      </Grid>

      {/* Quick Actions */}
      <Box sx={{ display: "flex", gap: 2, mb: 4 }}>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setCreateOpen(true)}
          size="large"
          sx={{ px: 3 }}
        >
          New Project
        </Button>
        <Button
          variant="outlined"
          startIcon={<OpenIcon />}
          onClick={() => navigate("/project")}
          size="large"
        >
          Open Project
        </Button>
      </Box>

      {/* Recent Projects */}
      <Box>
        <Typography variant="h6" fontWeight={700} gutterBottom>
          Recent Projects
        </Typography>
        {isLoading ? (
          <Grid container spacing={2}>
            {Array.from({ length: 6 }).map((_, i) => (
              <Grid item xs={12} sm={6} md={4} key={i}>
                <Skeleton variant="rounded" height={200} />
              </Grid>
            ))}
          </Grid>
        ) : recentProjects.length === 0 ? (
          <Card>
            <CardContent sx={{ py: 6, textAlign: "center" }}>
              <VideoIcon sx={{ fontSize: 56, color: "text.disabled", mb: 2 }} />
              <Typography variant="h6" color="text.secondary">
                No projects yet
              </Typography>
              <Typography variant="body2" color="text.disabled" sx={{ mb: 3 }}>
                Create your first faceless video project to get started
              </Typography>
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={() => setCreateOpen(true)}
              >
                Create First Project
              </Button>
            </CardContent>
          </Card>
        ) : (
          <Grid container spacing={2}>
            {recentProjects.map((project) => {
              const override = progressOverrides[project.id];
              const mergedProject = override
                ? { ...project, progress_state: { ...project.progress_state, ...override } }
                : project;
              return (
                <Grid item xs={12} sm={6} md={4} key={project.id}>
                  <ProjectCard
                    project={mergedProject}
                    onOpen={handleOpen}
                    onArchive={handleArchive}
                    onDelete={handleDelete}
                    onDuplicate={handleDuplicate}
                    onRename={handleRename}
                  />
                </Grid>
              );
            })}
          </Grid>
        )}
      </Box>

      {/* Rename Dialog */}
      <ProjectRenameDialog
        open={!!renameTarget}
        project={renameTarget}
        onClose={() => setRenameTarget(null)}
      />

      {/* Create Project Dialog */}
      <Dialog
        open={createOpen}
        onClose={() => { setCreateOpen(false); setCreateNameError(""); setNewProjectType("deep_dive"); }}
        maxWidth="sm"
        fullWidth
        PaperProps={{ sx: { bgcolor: "#1A1A2E" } }}
      >
        <DialogTitle fontWeight={700}>Create New Project</DialogTitle>
        <DialogContent sx={{ pt: 1 }}>
          {/* Project Type selector */}
          <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: "block", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.8 }}>
            Project Type
          </Typography>
          <Box sx={{ display: "flex", gap: 1.5, mb: 2.5 }}>
            {([
              { value: "deep_dive" as const, label: "Deep Dive", desc: "Long-form educational content" },
              { value: "ai_news" as const,   label: "AI News",   desc: "Daily 10-point news roundup" },
            ]).map(({ value, label, desc }) => (
              <Box
                key={value}
                onClick={() => setNewProjectType(value)}
                sx={{
                  flex: 1,
                  p: 1.5,
                  borderRadius: 2,
                  border: "2px solid",
                  borderColor: newProjectType === value ? "primary.main" : "rgba(255,255,255,0.1)",
                  bgcolor: newProjectType === value ? "rgba(108,99,255,0.12)" : "transparent",
                  cursor: "pointer",
                  transition: "border-color 0.15s, background-color 0.15s",
                  "&:hover": { borderColor: "primary.light", bgcolor: "rgba(108,99,255,0.06)" },
                }}
              >
                <Typography variant="subtitle2" fontWeight={700} gutterBottom={false}>
                  {label}
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block">
                  {desc}
                </Typography>
              </Box>
            ))}
          </Box>

          <TextField
            autoFocus
            fullWidth
            label="Project Name"
            value={newProjectName}
            onChange={(e) => { setNewProjectName(e.target.value); if (createNameError) setCreateNameError(""); }}
            onKeyDown={(e) => e.key === "Enter" && handleCreateProject()}
            sx={{ mb: 2 }}
            placeholder={newProjectType === "ai_news" ? "e.g. AI News — June 25" : "e.g. AI in 2025"}
            error={!!createNameError}
            helperText={createNameError || undefined}
          />
          <TextField
            fullWidth
            label="Description (optional)"
            value={newProjectDesc}
            onChange={(e) => setNewProjectDesc(e.target.value)}
            multiline
            rows={2}
            placeholder="Brief description of your video topic"
            sx={{ mb: 2 }}
          />
          <FormControl fullWidth>
            <InputLabel>Video Language</InputLabel>
            <Select
              value={newProjectLang}
              label="Video Language"
              onChange={(e) => setNewProjectLang(e.target.value)}
            >
              <MenuItem value="en">English (no translation)</MenuItem>
              <MenuItem value="te">Telugu</MenuItem>
              <MenuItem value="hi">Hindi</MenuItem>
              <MenuItem value="ta">Tamil</MenuItem>
              <MenuItem value="kn">Kannada</MenuItem>
              <MenuItem value="ml">Malayalam</MenuItem>
              <MenuItem value="bn">Bengali</MenuItem>
              <MenuItem value="mr">Marathi</MenuItem>
              <MenuItem value="gu">Gujarati</MenuItem>
              <MenuItem value="fr">French</MenuItem>
              <MenuItem value="de">German</MenuItem>
              <MenuItem value="es">Spanish</MenuItem>
              <MenuItem value="ja">Japanese</MenuItem>
              <MenuItem value="ko">Korean</MenuItem>
              <MenuItem value="zh-CN">Chinese (Simplified)</MenuItem>
            </Select>
          </FormControl>
          {newProjectLang !== "en" && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
              Script, scenes, and SEO files will be auto-translated before voice generation. Image prompts stay in English.
            </Typography>
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleCreateProject}
            disabled={!newProjectName.trim() || createProject.isPending}
            startIcon={createProject.isPending ? <CircularProgress size={16} /> : undefined}
          >
            Create Project
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
