export interface ScriptSegment {
  id: string;
  clip_index: number;
  act: string;
  video_start: number;
  video_end: number;
  duration: number;
  video_start_fmt: string;
  video_end_fmt: string;
  vod_start: number;
  vod_end: number;
  vod_start_fmt: string;
  vod_end_fmt: string;
  scene_note: string;
  dialogue_hindi: string;
  pacing: string;
  word_count: number;
  target_words: number;
}

export interface StreamMetadata {
  id: string;
  url: string;
  title: string;
  channel: string;
  duration: number;
  thumbnail: string;
  view_count: number;
  description: string;
  is_mock?: boolean;
}

export interface JobState {
  id: string;
  url: string;
  target_minutes: number;
  story_style: string;
  voice_speaker?: string;
  status: "IDLE" | "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED";
  stage: number;
  progress: number;
  message: string;
  metadata?: StreamMetadata;
  segments?: ScriptSegment[];
  stitched_video_url?: string;
  final_video_url?: string;
  game_audio_video_url?: string;
  srt_url?: string;
  voice_mode?: "SELF_RECORDED";
  error?: string;
}
