import { createTheme, alpha } from "@mui/material/styles";

declare module "@mui/material/styles" {
  interface Palette {
    surface: Palette["primary"];
  }
  interface PaletteOptions {
    surface?: PaletteOptions["primary"];
  }
}

const theme = createTheme({
  palette: {
    mode: "dark",
    primary: {
      main: "#6C63FF",
      light: "#9C94FF",
      dark: "#4A44CC",
      contrastText: "#FFFFFF",
    },
    secondary: {
      main: "#00BCD4",
      light: "#4DD0E1",
      dark: "#0097A7",
      contrastText: "#FFFFFF",
    },
    background: {
      default: "#0A0A0F",
      paper: "#12121A",
    },
    surface: {
      main: "#1A1A2E",
      light: "#22223A",
      dark: "#12121F",
    },
    error: {
      main: "#FF5252",
      light: "#FF7979",
      dark: "#C62828",
    },
    warning: {
      main: "#FFB300",
      light: "#FFD54F",
      dark: "#E65100",
    },
    success: {
      main: "#00E676",
      light: "#69F0AE",
      dark: "#00C853",
    },
    info: {
      main: "#29B6F6",
      light: "#4FC3F7",
      dark: "#0288D1",
    },
    text: {
      primary: "#E8E8F0",
      secondary: "#9090A8",
      disabled: "#505068",
    },
    divider: "rgba(255,255,255,0.08)",
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h1: { fontWeight: 700, letterSpacing: "-0.02em" },
    h2: { fontWeight: 700, letterSpacing: "-0.01em" },
    h3: { fontWeight: 600 },
    h4: { fontWeight: 600 },
    h5: { fontWeight: 600 },
    h6: { fontWeight: 600 },
    subtitle1: { fontWeight: 500 },
    subtitle2: { fontWeight: 500 },
    body1: { fontWeight: 400, lineHeight: 1.6 },
    body2: { fontWeight: 400, lineHeight: 1.5 },
    button: { fontWeight: 600, textTransform: "none", letterSpacing: "0.01em" },
    caption: { fontWeight: 400, color: "#9090A8" },
  },
  shape: {
    borderRadius: 12,
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          scrollbarWidth: "thin",
          scrollbarColor: "#333355 transparent",
          "&::-webkit-scrollbar": { width: "6px" },
          "&::-webkit-scrollbar-track": { background: "transparent" },
          "&::-webkit-scrollbar-thumb": {
            backgroundColor: "#333355",
            borderRadius: "3px",
          },
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundImage: "none",
          backgroundColor: "#12121A",
          border: "1px solid rgba(255,255,255,0.06)",
          borderRadius: 16,
          "&:hover": {
            borderColor: "rgba(108,99,255,0.3)",
          },
          transition: "border-color 0.2s ease",
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          padding: "8px 20px",
          fontWeight: 600,
        },
        contained: {
          boxShadow: "none",
          "&:hover": { boxShadow: "0 4px 16px rgba(108,99,255,0.4)" },
        },
        outlined: {
          borderColor: "rgba(108,99,255,0.4)",
          "&:hover": {
            borderColor: "#6C63FF",
            backgroundColor: "rgba(108,99,255,0.08)",
          },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          fontWeight: 500,
          fontSize: "0.75rem",
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          borderRadius: 4,
          height: 6,
          backgroundColor: "rgba(255,255,255,0.06)",
        },
        bar: {
          borderRadius: 4,
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: "none",
          backgroundColor: "#12121A",
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          backgroundColor: "#0E0E18",
          borderRight: "1px solid rgba(255,255,255,0.06)",
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: "#0A0A0F",
          backgroundImage: "none",
          borderBottom: "1px solid rgba(255,255,255,0.06)",
          boxShadow: "none",
        },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          marginBottom: 2,
          "&.Mui-selected": {
            backgroundColor: "rgba(108,99,255,0.15)",
            borderLeft: "3px solid #6C63FF",
            "&:hover": { backgroundColor: "rgba(108,99,255,0.2)" },
          },
          "&:hover": { backgroundColor: "rgba(255,255,255,0.05)" },
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          "& .MuiOutlinedInput-root": {
            borderRadius: 10,
            "& fieldset": { borderColor: "rgba(255,255,255,0.12)" },
            "&:hover fieldset": { borderColor: "rgba(108,99,255,0.4)" },
            "&.Mui-focused fieldset": { borderColor: "#6C63FF" },
          },
        },
      },
    },
    MuiSelect: {
      styleOverrides: {
        root: {
          borderRadius: 10,
        },
      },
    },
    MuiAccordion: {
      styleOverrides: {
        root: {
          backgroundColor: "#1A1A2E",
          border: "1px solid rgba(255,255,255,0.06)",
          borderRadius: "12px !important",
          marginBottom: 8,
          "&:before": { display: "none" },
        },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          backgroundColor: "#22223A",
          border: "1px solid rgba(255,255,255,0.1)",
          fontSize: "0.75rem",
        },
      },
    },
  },
});

export default theme;
