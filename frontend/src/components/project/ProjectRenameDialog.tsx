import React, { useState, useEffect } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Button,
  CircularProgress,
  Typography,
} from "@mui/material";
import { useUpdateProject } from "../../hooks/useProjects";
import { Project } from "../../store/projectStore";

interface ProjectRenameDialogProps {
  open: boolean;
  project: Project | null;
  onClose: () => void;
  onSuccess?: (project: Project) => void;
}

export default function ProjectRenameDialog({
  open,
  project,
  onClose,
  onSuccess,
}: ProjectRenameDialogProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const updateProject = useUpdateProject();

  useEffect(() => {
    if (project && open) {
      setName(project.name);
      setDescription(project.description || "");
    }
  }, [project, open]);

  const handleSave = async () => {
    if (!project || !name.trim()) return;
    try {
      const updated = await updateProject.mutateAsync({
        id: project.id,
        data: { name: name.trim(), description: description.trim() || undefined },
      });
      onSuccess?.(updated);
      onClose();
    } catch {
      // error handled by mutation
    }
  };

  const hasChanges =
    name.trim() !== project?.name ||
    description.trim() !== (project?.description || "");

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      PaperProps={{ sx: { bgcolor: "#1A1A2E" } }}
    >
      <DialogTitle fontWeight={700}>Rename Project</DialogTitle>
      <DialogContent sx={{ pt: 1 }}>
        <TextField
          autoFocus
          fullWidth
          label="Project Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && hasChanges && handleSave()}
          sx={{ mb: 2, mt: 1 }}
          inputProps={{ maxLength: 255 }}
          helperText={`${name.length}/255`}
        />
        <TextField
          fullWidth
          label="Description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          multiline
          rows={2}
          placeholder="Brief description of your video topic"
        />
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} disabled={updateProject.isPending}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handleSave}
          disabled={!name.trim() || !hasChanges || updateProject.isPending}
          startIcon={updateProject.isPending ? <CircularProgress size={16} /> : undefined}
        >
          Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}
