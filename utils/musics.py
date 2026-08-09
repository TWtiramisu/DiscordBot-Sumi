import yt_dlp

YTDL_OPTIONS = {
    'format': 'ba/ba*/bestaudio/best', # 優先選擇純音訊軌
    'extract_flat': 'in_playlist', # 快速載入清單
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/115.0.0.0 Safari/537.36',
        'Referer': 'https://www.bilibili.com/'
    }
}

FFMPEG_OPTIONS = {
    'before_options': (
        '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 '
        '-probesize 10000000 -analyzeduration 10000000 '
        '-headers "Referer: https://www.bilibili.com/\r\n'
        'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/115.0.0.0 Safari/537.36\r\n"'
    ),
    # -ar 48000 (固定 48kHz, 解決加速問題), -ac 2 (雙聲道)
    'options': '-vn -ar 48000 -ac 2'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)