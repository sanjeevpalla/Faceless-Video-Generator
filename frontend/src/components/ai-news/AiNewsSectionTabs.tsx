import React from "react";
import { Box, Tabs, Tab, Chip } from "@mui/material";
import { SectionContent } from "../../api/aiNews";

interface Props {
  sections: SectionContent[];
  selected: string | null;
  onSelect: (label: string | null) => void;
}

function sectionShortLabel(sec: SectionContent): string {
  if (sec.type === "intro") return "Intro";
  if (sec.type === "outro") return "Outro";
  return `S${sec.order - 1}`;
}

export default function AiNewsSectionTabs({ sections, selected, onSelect }: Props) {
  const tabIndex = selected === null ? 0 : (sections.findIndex((s) => s.label === selected) + 1) || 0;

  return (
    <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
        <Chip
          label="AI NEWS SECTIONS"
          size="small"
          color="warning"
          variant="outlined"
          sx={{ fontSize: "0.6rem", height: 18 }}
        />
      </Box>
      <Tabs
        value={tabIndex}
        onChange={(_, v: number) => onSelect(v === 0 ? null : sections[v - 1]?.label ?? null)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{
          minHeight: 32,
          "& .MuiTab-root": { minHeight: 32, py: 0.5, fontSize: "0.72rem", minWidth: 52, px: 1.5 },
        }}
      >
        <Tab label="All" />
        {sections.map((sec) => (
          <Tab key={sec.label} label={sectionShortLabel(sec)} title={sec.title} />
        ))}
      </Tabs>
    </Box>
  );
}
