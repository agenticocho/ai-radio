%include "config.liq"

base_dir = path.dirname(argv(0))
audio_dir = path.concat(base_dir, "audio")
hls_dir = path.concat(base_dir, "hls")

let {px, vw, vh, rem, width, height} = video.canvas.virtual_10k.actual_720p

video.frame.width := width
video.frame.height := height

## Telnet server for curator pushes
settings.server.telnet := true
settings.server.telnet.port := 1234
settings.server.telnet.bind_addr := "127.0.0.1"

## Curator push queue — receives narration + stretched track from curator.sh
request_queue = request.queue(id="request_queue")

## Local playlist — base source, shuffled, loops forever
local = mksafe(playlist.safe(audio_dir, reload=60, mode="randomize", id="audio", mime_type="audio/mpeg"))

## Priority: curator queue first, local playlist as fallback
radio = fallback(track_sensitive=true, [request_queue, local])

## Log every track start to /tmp/agentdj.log
radio.on_track(synchronous=false, fun (m) ->
  begin
    title  = m["title"]
    artist = m["artist"]
    fname  = m["filename"]
    log_line = "TRACK title=#{title} artist=#{artist} file=#{fname}"
    _ = process.run("echo #{string.quote(log_line)} >> /tmp/agentdj.log")
  end
)

## HLS output
enc = %ffmpeg(
  format = "mpegts",
  %audio(codec = "aac", b = "192k")
)

streams = [("radio", enc)]

output.file.hls(segment_duration=2., hls_dir, streams, radio)
