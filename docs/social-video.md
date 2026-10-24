# Social clip

No final clip exists yet. Keep the current static poster and add no video URL
until the manager has watched the actual clip and accepted it before commit.

Record 10–15 seconds of the accepted scene with assets loaded and no private
browser UI. Retain that recording with a short note of the scene revision, view
and review decision. Prepare an ordinary silent MP4 and matching poster:

```sh
mkdir -p public/social
ffmpeg -i recording.webm -t 15 -an -vf "scale='min(1280,iw)':-2,drawtext=text='@jjpcodes':fontsize=24:fontcolor=white:shadowcolor=black:shadowx=1:shadowy=1:x=w-tw-24:y=h-th-20" -r 30 -c:v libx264 -crf 21 -pix_fmt yuv420p -movflags +faststart public/social/preview.mp4
ffmpeg -ss 1 -i public/social/preview.mp4 -frames:v 1 -q:v 2 public/social/poster.jpg
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 public/social/preview.mp4
```

After review, commit these assets and add static `og:video` and
`og:video:secure_url` pointing to `https://010.jjpcodes.com/social/preview.mp4`,
`og:video:type` of `video/mp4`, and the actual width/height to `public/index.html`.
Point its `og:image` and `og:image:secure_url` at the matching HTTPS poster and
update image dimensions/alt. Keep `summary_large_image` for static fallback.
No manifest, build gate or player integration is needed.

`public/_headers` supplies MIME types and revalidation for ordinary public assets.
Once the real clip is available on the candidate server, run:

```sh
node scripts/verify-social-video.mjs https://actual-candidate.example
```

This checks the HTML/poster, video MIME/length and a real 1,024-byte range response
(`206`, correct `Content-Range`, MP4 bytes). It uses the supplied candidate origin
for asset requests. Exit code 2 means only the static fallback exists; final video
verification remains pending. Publication still needs manager approval. Social
platforms decide whether to display video or the fallback poster.
