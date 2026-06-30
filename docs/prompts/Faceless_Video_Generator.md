# ROLE

You are a:

- Principal Software Architect
- Senior Python Engineer
- Senior Frontend Engineer
- AI Engineer
- UX/UI Designer
- DevOps Engineer
- Product Designer
- Desktop Application Architect

Your task is to design and implement a complete production-grade desktop application for automated faceless video generation.

The application must be:
- Professional
- Modern
- Beautiful
- Scalable
- Maintainable
- Modular
- Production-ready
- Suitable for daily use by content creators

---

# PROJECT NAME

Faceless Video Generator

---

# PROJECT GOAL

Build a desktop application that converts user-provided content assets into a complete professional faceless YouTube-style video.

The application must:
- Run locally
- Work offline after installation
- Use local AI models
- Minimize recurring costs
- Produce professional-quality videos
- Support multiple niches
- Provide a modern graphical user interface
- Provide real-time progress tracking
- Support long-form documentary content
- Support short-form content in future releases

---

## APPLICATION SCOPE

This application must be generic and reusable.

It must NOT contain any niche-specific branding.

Supported niches include:
- Artificial Intelligence
- Technology
- Business
- Finance
- Investing
- History
- Science
- Education
- Health
- Space
- News
- Motivation
- Travel
- Tutorials
- Product Reviews
- Documentaries
- General YouTube Content

The application should work entirely from user-provided input files.

---

# USER HARDWARE

GPU:
RTX 5060 Ti 16GB

RAM:
64GB DDR5

CPU:
AMD Ryzen 7

SSD:
1TB NVMe

OS:
Windows 11

---

# ARCHITECTURE REQUIREMENTS

Build the application using:

Frontend:

* React
* TypeScript
* Material UI

Desktop Framework:

* Tauri (preferred)

Backend:

* Python
* FastAPI

Database:

* SQLite

Video Processing:

* MoviePy
* FFmpeg

Image Generation:

* Local FLUX Dev

Voice Generation:

* Piper TTS

Subtitle Generation:

* Whisper

Progress Updates:

* WebSockets

---

# IMPORTANT CONSTRAINTS

DO NOT use:

* OpenAI API
* Gemini API
* Anthropic API
* ElevenLabs API
* Runway API
* Pika API
* Any paid SaaS dependency

The user manually generates content using Gemini Pro Web UI.

The application starts after the user prepares the required input files.

---

# INPUT FILES

The user uploads:

1. script.md

2. scenes.json

    ## scenes.json SCHEMA

    {
        "video_title": "Title",
        "total_duration": 600,
        "scenes":[
                    {
                    "scene_id": 1,
                    "title": "Opening Hook",
                    "image_file": "scene_001.png",
                    "duration": 12,
                    "narration": "Narration text",
                    "visual_description": "Opening scene, cinematic shot of a futuristic city with flying cars",
                    "section": "Title Card"
                    }
                ]
    }


3. image_prompts.txt

4. thumbnail_prompt.txt

5. seo.json

    ## seo.json SCHEMA
    {
        "title": "",
        "alternate_titles": [],
        "description": "",
        "tags": [],
        "hashtags": [],
        "chapters": [],
        "keywords": [],
        "search_intent": "",
        "ctr_estimate": ""
}


6. bg_music.mp3

---

# APPLICATION WORKFLOW

STEP 1

User creates a project.

STEP 2

User uploads all required files.

STEP 3

Application validates files.

STEP 4

Generate Scene Images using FLUX Dev.

STEP 5

Generate Thumbnail using FLUX Dev.

STEP 6

Generate Voiceover using Piper.

STEP 7

Generate Subtitles using Whisper.

STEP 8

Generate Final Video using MoviePy and FFmpeg.

STEP 9

Generate YouTube metadata.

STEP 10

Preview outputs.

STEP 11

Upload to YouTube.

---

# USER INTERFACE REQUIREMENTS

Design a professional modern UI.

The UI should feel similar to:

Professional creative software.

Requirements:

* Responsive layout
* Dark mode
* Modern cards
* Progress indicators
* Status badges
* Project management
* Live logs
* Image previews
* Video preview
* Thumbnail preview

---

# APPLICATION PAGES

## Dashboard

Display:

* Project Name
* Project Status
* Recent Projects
* Last Generated Video
* Overall Progress

Actions:

* New Project
* Open Project
* Generate All

---

## Project Page

Display:

Uploaded Files

script.md

scenes.json

image_prompts.txt

thumbnail_prompt.txt

seo.json

bg_music.mp3

Status:

READY
MISSING
PROCESSING
FAILED
COMPLETED

---

## Image Generation Page

Display:

* Total scenes
* Generated images
* Remaining images

Image gallery grid

Preview image

Regenerate image

Generate all

Progress bar

---

## Voice Generation Page

Display:

* Selected voice
* Estimated duration
* Voice generation progress

Audio preview

Regenerate voice

---

## Subtitle Page

Display:

* Subtitle preview
* Timeline preview

Export SRT

Export VTT

---

## Thumbnail Page

Display:

Thumbnail preview

Regenerate thumbnail

Export thumbnail

---

## Video Generation Page

Display:

* Scene progress
* Render progress
* Estimated completion time

Preview final video

Open output folder

Export MP4

---

## Settings Page

FLUX Settings

* Resolution
* Steps
* CFG
* Sampler

Piper Settings

* Voice
* Speed

Video Settings

* FPS
* Resolution
* Zoom Amount
* Transition Duration
* Subtitle Style

Output Settings

* Export Folder
* Naming Convention

---

# PROJECT MANAGEMENT

Support:

Create Project

Open Project

Rename Project

Duplicate Project

Archive Project

Delete Project

Resume Project

---

# FILE STRUCTURE

Generate complete source code.

Structure:

frontend/

backend/

database/

config/

logs/

projects/

outputs/

docs/

tests/

---

# PROJECT DATA STRUCTURE

Each project should maintain:

Project Metadata

Input Files

Generated Images

Generated Audio

Generated Subtitles

Generated Thumbnail

Generated Video

Logs

Progress State

Resume State

---

# IMAGE GENERATION

Implement:

ImageGenerationService

Requirements:

* Read image_prompts.txt
* Generate images using local FLUX Dev
* Save images
* Retry failed generations
* Resume support
* Progress tracking
* Preview support

## Image Generation Backend

Use ComfyUI as the image generation backend.

Requirements:

- Connect to local ComfyUI API
- Submit FLUX Dev generation jobs
- Monitor progress
- Download generated images
- Handle failures
- Retry failed jobs
- Support custom workflows
- Support workflow templates

Do NOT load FLUX models directly inside FastAPI.

ComfyUI should manage model execution.

---

# THUMBNAIL GENERATION

Implement:

ThumbnailGenerationService

Requirements:

* Read thumbnail_prompt.txt
* Generate thumbnail
* Save thumbnail
* Preview thumbnail

---

# VOICE GENERATION

Implement:

VoiceGenerationService

Requirements:

* Read narration from scenes.json
* Generate voice using Piper
* Merge into single voiceover.mp3
* Progress tracking

---

# SUBTITLE GENERATION

Implement:

SubtitleGenerationService

Requirements:

* Use local Whisper
* Generate SRT
* Generate VTT
* Preview subtitles

---

# VIDEO GENERATION

Implement:

VideoGenerationService

Requirements:

Professional documentary style.

Features:

* Ken Burns effect
* Pan animations
* Zoom animations
* Scene transitions
* Fade effects
* Subtitle overlays
* Background music mixing
* Intro screen
* Outro screen
* Scene title overlays
* Chapter markers

Output:

1080p

30 FPS

MP4

## Video Style System

Create reusable video templates:

- Documentary
- News
- Technology
- Finance
- Educational
- History

Each template should define:

- Transition style
- Subtitle style
- Zoom speed
- Animation style
- Intro style
- Outro style
- Music mixing levels
- Text overlay style

Templates should be configurable through the UI.

---

# SCENE TIMING ENGINE

The application must automatically determine:

- Image duration
- Scene duration
- Voiceover duration
- Subtitle timing

Priority Order:

1. Voiceover duration
2. Scene duration from scenes.json
3. Fallback duration rules

Generate the complete video timeline automatically.

---

# PLUGIN ARCHITECTURE

Design all generators as plugins.

Supported Plugin Types:

- Image Generators
- Voice Generators
- Subtitle Generators
- Video Effects
- Metadata Generators

Future plugins should be installable without modifying core application code.

---

# BATCH PROCESSING

Support:

- Queue Projects
- Multiple Project Processing
- Overnight Rendering
- Priority Scheduling
- Pause Queue
- Resume Queue

Display queue status in the UI.

---

# PROJECT STORAGE STRUCTURE

Each project must use:

project_id/

    input/

    images/

    audio/

    subtitles/

    thumbnails/

    output/

    logs/

    metadata/

    temp/

All generated files must remain isolated per project.

---

# FUTURE AI AGENT SUPPORT

Design architecture for future AI automation.

Create abstractions:

- ContentGenerationProvider
- ResearchProvider
- ScriptProvider
- SceneProvider
- PromptGenerationProvider
- SEOProvider

These providers will allow future integration of:

- Gemini
- Claude
- GPT
- Local LLMs

without changing core application code.

---

# VIDEO PREVIEW SYSTEM

Support:

- Scene Preview
- Audio Preview
- Subtitle Preview
- Thumbnail Preview
- Full Video Preview

Preview should be available before final export whenever possible.

---

# PERFORMANCE TARGETS

Target Hardware:

RTX 5060 Ti 16GB

Requirements:

- 50 scene images generated under 20 minutes
- Voice generation under 2 minutes
- Subtitle generation under 3 minutes
- 10 minute documentary rendered under 15 minutes

Optimize for GPU utilization and efficient resource usage.

---

# YOUTUBE METADATA

Implement:

MetadataService

Read:

seo.json

Generate:

youtube_metadata.json

---

# REAL-TIME PROGRESS TRACKING

Every service must provide progress.

Display:

Current Step

Percentage

Completed Items

Remaining Items

Estimated Time

Use:

WebSockets

---

# LOGGING

Create centralized logging.

Levels:

INFO

WARNING

ERROR

DEBUG

Display logs inside UI.

---

# DATABASE

Use SQLite.

Store:

Projects

Settings

Generation History

Logs

Resume State

---

# ERROR HANDLING

Implement:

Validation

Recovery

Retry Logic

Graceful Failures

Resume Support

---

# TESTING

Generate:

Unit Tests

Integration Tests

Service Tests

Frontend Tests

Mock Implementations

---

# DOCUMENTATION

Generate:

README.md

Architecture Diagram

Installation Guide

Developer Guide

User Guide

Troubleshooting Guide

Deployment Guide

---

# OUTPUT REQUIREMENT

Produce:

1. Complete software architecture
2. Complete folder structure
3. Database schema
4. Backend implementation
5. Frontend implementation
6. Service layer implementation
7. Configuration system
8. WebSocket progress system
9. Complete source code
10. Tests
11. Documentation

--- 

## TECHNICAL REQUIREMENTS

### Backend Requirements

- FastAPI application
- Python 3.11+
- Pydantic models for validation
- Type hints throughout
- Dependency injection system
- Robust error handling
- Logging (INFO, WARNING, ERROR, DEBUG)
- Graceful shutdown handling
- REST API endpoints for all services
- WebSocket endpoints for progress tracking

### Frontend Requirements

- React with TypeScript
- Material UI v5+
- Functional components
- React Query for data fetching
- Zustand for global state
- Responsive design
- Dark mode theme
- Real-time WebSocket updates
- Form validation
- Loading states
- Error boundaries
- Image gallery grid
- Video player with preview
- Progress bar with percentage
- Status badges
- Live log viewer

### Database Requirements

- SQLite database
- Projects table
- Settings table
- Generation history table
- Logs table
- Resume state table

### Integration Requirements

- FLUX Dev integration
- Piper TTS integration
- Whisper integration
- MoviePy + FFmpeg integration
- WebSocket integration
- YouTube API integration (optional later)

### Deployment Requirements

- Tauri desktop application
- Cross-platform compatibility (Windows, macOS, Linux)
- Auto-update support (future)
- Single-file executable
- Offline functionality after installation

---

## DEVELOPMENT APPROACH

DO NOT generate the entire application in a single response.

Build incrementally using milestones:

Phase 1:
- Architecture
- Folder Structure
- Database Schema
- Technology Decisions
- Project Setup

Phase 2:
- Backend Foundation
- FastAPI Setup
- Configuration System
- Models
- Dependency Injection
- Logging

Phase 3:
- Frontend Foundation
- React Setup
- Material UI Design System
- Layout
- Navigation
- State Management

Phase 4:
- Project Management Module
- File Upload System
- Validation System
- Persistence Layer

Phase 5:
- FLUX Dev Integration
- Image Generation
- Thumbnail Generation

Phase 6:
- Piper Integration
- Voice Generation

Phase 7:
- Whisper Integration
- Subtitle Generation

Phase 8:
- MoviePy + FFmpeg Integration
- Rendering Engine
- Effects Engine

Phase 9:
- WebSocket Progress Tracking
- Live UI Updates
- Logging Dashboard

Phase 10:
- YouTube Upload Integration
- Metadata Management

Phase 11:
- Testing
- Optimization
- Error Recovery
- Resume Support

Phase 12:
- Documentation
- Packaging
- Deployment
- Release Preparation

For every phase:
1. Explain architecture
2. Explain design decisions
3. Generate complete code
4. Generate tests
5. Generate documentation

Generate production-ready implementations only.

Do not generate pseudocode.

# NON-FUNCTIONAL REQUIREMENTS

Maintainability:
- SOLID principles
- Clean Architecture
- Repository Pattern
- Service Layer Pattern

Performance:
- Async operations
- Background workers
- GPU utilization

Reliability:
- Retry logic
- Resume support
- Crash recovery

Observability:
- Structured logs
- Metrics
- Progress tracking

# ASSET CACHE SYSTEM

Hash prompts.

Reuse images when prompt hash matches.

Reuse voice segments when narration hash matches.

Reuse subtitles when audio hash matches.

Avoid unnecessary regeneration.

# JOB QUEUE ARCHITECTURE

All generation tasks must execute through a queue system.

Support:

- pending
- running
- paused
- completed
- failed

Queue manager coordinates image, voice, subtitle and render jobs.

## FINAL ASSUMPTION

Assume this application will be used daily by content creators to generate professional faceless videos across multiple niches and channels at scale.
