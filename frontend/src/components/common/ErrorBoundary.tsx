import React, { Component, ErrorInfo, ReactNode } from "react";
import { Box, Button, Card, CardContent, Typography } from "@mui/material";
import { ErrorOutline as ErrorIcon, Refresh as RefreshIcon } from "@mui/icons-material";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error("[ErrorBoundary] Caught error:", error, errorInfo);
    this.setState({ errorInfo });
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            minHeight: 400,
            p: 3,
          }}
        >
          <Card sx={{ maxWidth: 560, width: "100%" }}>
            <CardContent sx={{ p: 4, textAlign: "center" }}>
              <ErrorIcon
                sx={{ fontSize: 56, color: "error.main", mb: 2 }}
              />
              <Typography variant="h5" fontWeight={700} gutterBottom>
                Something went wrong
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                An unexpected error occurred in this component.
              </Typography>
              {this.state.error && (
                <Box
                  sx={{
                    bgcolor: "rgba(255,82,82,0.08)",
                    border: "1px solid rgba(255,82,82,0.2)",
                    borderRadius: 2,
                    p: 2,
                    mb: 3,
                    textAlign: "left",
                  }}
                >
                  <Typography
                    variant="caption"
                    sx={{
                      fontFamily: "monospace",
                      color: "error.light",
                      wordBreak: "break-all",
                      display: "block",
                    }}
                  >
                    {this.state.error.toString()}
                  </Typography>
                </Box>
              )}
              <Button
                variant="contained"
                startIcon={<RefreshIcon />}
                onClick={this.handleReset}
              >
                Try Again
              </Button>
            </CardContent>
          </Card>
        </Box>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
