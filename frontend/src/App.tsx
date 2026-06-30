import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import AppLayout from "./components/layout/AppLayout";
import ErrorBoundary from "./components/common/ErrorBoundary";
import Dashboard from "./pages/Dashboard";
import ProjectPage from "./pages/ProjectPage";
import ImageGenPage from "./pages/ImageGenPage";
import ClipsPage from "./pages/ClipsPage";
import VoiceGenPage from "./pages/VoiceGenPage";
import SubtitlePage from "./pages/SubtitlePage";
import ThumbnailPage from "./pages/ThumbnailPage";
import VideoGenPage from "./pages/VideoGenPage";
import SettingsPage from "./pages/SettingsPage";
import ContentGenPage from "./pages/ContentGenPage";
import AiNewsPage from "./pages/AiNewsPage";
import AiNewsClipsPage from "./pages/AiNewsClipsPage";

export default function App() {
  return (
    <ErrorBoundary>
      <AppLayout>
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/project" element={<ProjectPage />} />
            <Route path="/images" element={<ImageGenPage />} />
            <Route path="/clips" element={<ClipsPage />} />
            <Route path="/ai-news-clips" element={<AiNewsClipsPage />} />
            <Route path="/voice" element={<VoiceGenPage />} />
            <Route path="/subtitles" element={<SubtitlePage />} />
            <Route path="/thumbnail" element={<ThumbnailPage />} />
            <Route path="/video" element={<VideoGenPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/content" element={<Navigate to="/content/trends" replace />} />
            <Route path="/content/:step" element={<ContentGenPage />} />
            <Route path="/ai-news" element={<AiNewsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </ErrorBoundary>
      </AppLayout>
    </ErrorBoundary>
  );
}
