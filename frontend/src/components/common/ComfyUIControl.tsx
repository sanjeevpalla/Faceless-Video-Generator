import React, { useState } from "react";
import { Box, Button, Chip, CircularProgress, Tooltip } from "@mui/material";
import {
  Wifi as OnlineIcon,
  WifiOff as OfflineIcon,
  PlayArrow as StartIcon,
  Stop as StopIcon,
} from "@mui/icons-material";
import { useComfyUIStatus } from "../../hooks/useImages";
import { servicesApi } from "../../api/services";

export default function ComfyUIControl() {
  const { data, isLoading, refetch } = useComfyUIStatus();
  const [busy, setBusy] = useState<"starting" | "stopping" | null>(null);

  const online = data?.online ?? false;
  const vramFreeGb = (data as any)?.gpu_vram_free
    ? ((data as any).gpu_vram_free / 1024).toFixed(1)
    : null;
  const vramTotalGb = (data as any)?.gpu_vram_total
    ? ((data as any).gpu_vram_total / 1024).toFixed(1)
    : null;

  const handleStart = async () => {
    setBusy("starting");
    try {
      await servicesApi.startComfyUI();
      const iv = setInterval(async () => {
        const res = await refetch();
        if (res.data?.online) { clearInterval(iv); setBusy(null); }
      }, 5000);
      setTimeout(() => { clearInterval(iv); setBusy(null); }, 90_000);
    } catch {
      setBusy(null);
    }
  };

  const handleStop = async () => {
    setBusy("stopping");
    try {
      await servicesApi.stopComfyUI();
      setTimeout(async () => { await refetch(); setBusy(null); }, 2000);
    } catch {
      setBusy(null);
    }
  };

  const chip = isLoading ? (
    <Chip label="Checking ComfyUI…" size="small" sx={{ height: 22 }} />
  ) : (
    <Tooltip
      title={
        online
          ? `ComfyUI online${vramFreeGb ? ` · VRAM: ${vramFreeGb}GB free / ${vramTotalGb}GB total` : ""}`
          : "ComfyUI offline"
      }
    >
      <Chip
        icon={
          online
            ? <OnlineIcon sx={{ fontSize: "12px !important" }} />
            : <OfflineIcon sx={{ fontSize: "12px !important" }} />
        }
        label={
          online
            ? `ComfyUI Online${vramFreeGb ? ` · ${vramFreeGb}GB VRAM` : ""}`
            : "ComfyUI Offline"
        }
        size="small"
        sx={{
          height: 24,
          fontSize: "0.7rem",
          bgcolor: online ? "rgba(0,230,118,0.1)" : "rgba(255,82,82,0.1)",
          color: online ? "success.main" : "error.main",
          border: `1px solid ${online ? "rgba(0,230,118,0.3)" : "rgba(255,82,82,0.3)"}`,
        }}
      />
    </Tooltip>
  );

  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
      {chip}
      {!isLoading && (
        <Button
          size="small"
          variant="outlined"
          color={online ? "error" : "success"}
          startIcon={
            busy
              ? <CircularProgress size={12} color="inherit" />
              : online
              ? <StopIcon sx={{ fontSize: 14 }} />
              : <StartIcon sx={{ fontSize: 14 }} />
          }
          onClick={online ? handleStop : handleStart}
          disabled={!!busy}
          sx={{ height: 24, fontSize: "0.7rem", px: 1, minWidth: 0 }}
        >
          {busy === "starting" ? "Starting…" : busy === "stopping" ? "Stopping…" : online ? "Stop" : "Start"}
        </Button>
      )}
    </Box>
  );
}
