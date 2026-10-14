"""English translations; Korean source text is the stable message ID."""
EN = {'USB로 꽂은 기기의 소리를 Wi-Fi로 PC에서 듣고, PC 마이크를 그 기기에': 'Hear your USB device over Wi-Fi and send PC audio back to it.',
 'ESP32 주소': 'ESP32 address',
 'USB 모드 · 확인 중…': 'USB mode · Checking…',
 '보낼 소리 · PC 마이크 / 오디오 입력': 'Send audio · PC microphone / audio input',
 '100%로': 'Reset 100%',
 '기기 소리 · PC 이어폰 / 헤드폰': 'Device audio · PC earphones / headphones',
 '듣기 버퍼 · 클수록 안정적, 지연 증가': 'Listening buffer · More stability, more delay',
 '보낼 소리 음소거': 'Mute microphone',
 '기기 소리 음소거': 'Mute device audio',
 '듣기 크기': 'Listening volume',
 '보내는 음질…': 'Audio quality…',
 '보드 설정…': 'Board setup…',
 '연결 시작': 'Connect',
 '장치 새로고침': 'Refresh devices',
 '진단 저장': 'Save diagnostics',
 'ESP32의 USB 포트를 소리를 들을 기기에 연결하세요.': 'Connect the ESP32 USB port to your phone or other audio device.',
 '오디오 장치': 'Audio devices',
 '무음': 'Silent',
 '원래 크기': 'Original',
 '증폭': 'Boost',
 '줄이기': 'Reduced',
 '마이크 {v0}% · {v1}': 'Mic {v0}% · {v1}',
 '마이크 음량 저장': 'Save microphone volume',
 ' · PC에서 바꿈': ' · Set on PC',
 ' · 폰 볼륨': ' · Phone volume',
 '듣기 크기 · 무음': 'Listening · Muted',
 '듣기 크기 · {v0:.1f} dB': 'Listening · {v0:.1f} dB',
 '보드 설정': 'Board setup',
 '연결': 'Connection',
 '연결을 한 번 시작한 뒤 저장해 주세요.': 'Start a connection before saving diagnostics.',
 '연결 중지': 'Disconnect',
 '{v0} · AAC/송신 대기 약 {v1:.0f} ms\n추가 대기 추정치이며 전체 지연은 아니에요. · 송신 부족 {v2} · AAC 버림 {v3}': '{v0} · AAC/send queue '
                                                                                        '~{v1:.0f} ms\n'
                                                                                        'Extra queue estimate, not '
                                                                                        'total latency. · Send '
                                                                                        'underruns {v2} · AAC drops '
                                                                                        '{v3}',
 '입력 {v0} Hz → 전송 48000 Hz → 출력 {v1} Hz\n송신: 보냄 {v2} · 보드 수신 {v3} · 보드 버퍼 부족 {v4}\n듣기: 수신 {v5} · 버퍼 {v6} ms · 누락 {v7}\n듣기 버퍼 부족 {v8} · 출력 장치 오류 {v9} · 입력 버림 {v10}\n듣기 속도 보정 {v11:+.0f} ppm (−{v12}/+{v13} 프레임)': 'Input '
                                                                                                                                                                                                                  '{v0} '
                                                                                                                                                                                                                  'Hz '
                                                                                                                                                                                                                  '→ '
                                                                                                                                                                                                                  'Send '
                                                                                                                                                                                                                  '48000 '
                                                                                                                                                                                                                  'Hz '
                                                                                                                                                                                                                  '→ '
                                                                                                                                                                                                                  'Output '
                                                                                                                                                                                                                  '{v1} '
                                                                                                                                                                                                                  'Hz\n'
                                                                                                                                                                                                                  'Send: '
                                                                                                                                                                                                                  '{v2} '
                                                                                                                                                                                                                  'sent '
                                                                                                                                                                                                                  '· '
                                                                                                                                                                                                                  'Board '
                                                                                                                                                                                                                  'received '
                                                                                                                                                                                                                  '{v3} '
                                                                                                                                                                                                                  '· '
                                                                                                                                                                                                                  'Board '
                                                                                                                                                                                                                  'underruns '
                                                                                                                                                                                                                  '{v4}\n'
                                                                                                                                                                                                                  'Listen: '
                                                                                                                                                                                                                  '{v5} '
                                                                                                                                                                                                                  'received '
                                                                                                                                                                                                                  '· '
                                                                                                                                                                                                                  'Buffer '
                                                                                                                                                                                                                  '{v6} '
                                                                                                                                                                                                                  'ms '
                                                                                                                                                                                                                  '· '
                                                                                                                                                                                                                  'Missing '
                                                                                                                                                                                                                  '{v7}\n'
                                                                                                                                                                                                                  'Playback '
                                                                                                                                                                                                                  'underruns '
                                                                                                                                                                                                                  '{v8} '
                                                                                                                                                                                                                  '· '
                                                                                                                                                                                                                  'Output '
                                                                                                                                                                                                                  'errors '
                                                                                                                                                                                                                  '{v9} '
                                                                                                                                                                                                                  '· '
                                                                                                                                                                                                                  'Input '
                                                                                                                                                                                                                  'drops '
                                                                                                                                                                                                                  '{v10}\n'
                                                                                                                                                                                                                  'Playback '
                                                                                                                                                                                                                  'rate '
                                                                                                                                                                                                                  'correction '
                                                                                                                                                                                                                  '{v11:+.0f} '
                                                                                                                                                                                                                  'ppm '
                                                                                                                                                                                                                  '(−{v12}/+{v13} '
                                                                                                                                                                                                                  'frames)',
 '보내는 음질 · AAC 비교': 'Outbound audio quality · AAC comparison',
 '보내는 목소리의 질감': 'Shape your outgoing audio',
 '보내는 음성의 샘플레이트와 AAC 압축 음질을 조절해요.\n기기에서 돌아오는 소리는 변경하지 않아요.': 'Adjust the sample rate and AAC compression of outgoing '
                                                             'audio.\n'
                                                             'Audio returning from the device stays unchanged.',
 '원음 PCM · 추가 압축 없음': 'Original PCM · No extra compression',
 'AAC 압축·복원 · 실험': 'AAC encode/decode · Experimental',
 '처리 방식': 'Processing',
 '샘플레이트 · Hz': 'Sample rate · Hz',
 'AAC 비트레이트 · kbps': 'AAC bitrate · kbps',
 'AAC는 추가 지연이 생겨요. 낮은 샘플레이트일수록\n한 블록을 모으는 시간이 길어질 수 있어요.': 'AAC adds latency. Lower sample rates can take longer\n'
                                                           'to collect a complete audio block.',
 '기존 PCM 경로로 전송해요. AAC 처리를 거치지 않아요.': 'Send through the original PCM path without AAC processing.',
 '선택한 형식으로 AAC 압축 → 복원 → 48 kHz PCM 전송\n보드 USB 형식과 Wi-Fi 전송량은 그대로예요.\n통화·메신저 앱 자체의 녹음·압축 설정을 바꾸는 기능은 아니에요.': 'AAC '
                                                                                                             'encode → '
                                                                                                             'decode → '
                                                                                                             'send 48 '
                                                                                                             'kHz '
                                                                                                             'PCM.\n'
                                                                                                             'The USB '
                                                                                                             'format '
                                                                                                             'and '
                                                                                                             'Wi-Fi '
                                                                                                             'data '
                                                                                                             'rate '
                                                                                                             'stay '
                                                                                                             'unchanged.\n'
                                                                                                             'This '
                                                                                                             'does not '
                                                                                                             'change '
                                                                                                             'recording '
                                                                                                             'or codec '
                                                                                                             'settings '
                                                                                                             'in '
                                                                                                             'calling '
                                                                                                             'apps.',
 '연결을 중지한 뒤 음질 설정을 바꿀 수 있어요.': 'Disconnect before changing audio quality.',
 '음질 설정': 'Audio quality',
 '닫기': 'Close',
 '저장 · 다음 연결에 적용': 'Save for next connection',
 'Standard · Windows 호환': 'Standard · Windows compatible',
 'Apple · 아이폰 호환 (시험한 갤럭시도)': 'Apple · iPhone (also tested on Galaxy)',
 'Adaptive · 피드백 없음 (실험)': 'Adaptive · No feedback (experimental)',
 'ESP32 보드 설정': 'ESP32 Board Setup',
 '보드의 COM 포트(USB-시리얼)를 이 PC에 연결하세요. 처음 설정과 펌웨어 설치를 여기서 해요.': "Connect the board's COM (USB-serial) port to this PC to "
                                                             'configure it or install firmware.',
 '포트': 'Port',
 '다시 찾기': 'Refresh',
 '읽기': 'Read',
 '보드 자체 Wi-Fi': 'Board Wi-Fi',
 '이름': 'Name',
 '비밀번호': 'Password',
 '복사': 'Copy',
 '저장': 'Save',
 '무작위': 'Random',
 '비밀번호는 고쳐서 저장하거나 무작위로 만들 수 있어요 (8~63자, 영문·숫자·기호). 공유기 없이 휴대폰을 이 Wi-Fi에 바로 연결하면 보드 주소는 192.168.4.1이에요.': 'Save your '
                                                                                                         'own password '
                                                                                                         'or generate '
                                                                                                         'one (8–63 '
                                                                                                         'ASCII '
                                                                                                         'characters). '
                                                                                                         'When '
                                                                                                         'connecting '
                                                                                                         'directly to '
                                                                                                         'board Wi-Fi '
                                                                                                         'without a '
                                                                                                         'router, the '
                                                                                                         'board '
                                                                                                         'address is '
                                                                                                         '192.168.4.1.',
 '공유기 Wi-Fi (2.4 GHz)': 'Router Wi-Fi (2.4 GHz)',
 '지우기': 'Forget',
 'USB 모드': 'USB mode',
 '펌웨어': 'Firmware',
 '설정도 초기화 (새 보드 비밀번호, 공유기·USB 모드 지움)': 'Reset settings too (Wi-Fi password, router, USB mode)',
 '폴더 고르기…': 'Choose folder…',
 '펌웨어 설치': 'Install firmware',
 '이 프로그램 옆에 firmware 폴더가 없어요. 받은 펌웨어 폴더를 고르세요.': 'No firmware folder beside this app. Select your downloaded firmware '
                                                 'folder.',
 'COM 포트를 고르세요. 안 보이면 케이블과 USB-시리얼 드라이버를 확인하세요.': 'Select a COM port. If none appear, check the cable and USB-serial '
                                                  'driver.',
 '포트 목록을 못 읽었어요: {v0}': 'Could not list ports: {v0}',
 'COM 포트가 없어요. 보드의 COM 쪽 단자를 데이터 케이블로 연결하세요.': "No COM ports found. Connect the board's COM port with a data cable.",
 '보드용 USB-시리얼 칩이 안 보여요. 보드의 COM 단자를 연결하고 다시 찾기를 누르거나, 포트를 골라 읽기를 누르세요.': 'No known board USB-serial chip found. '
                                                                         'Connect its COM port and refresh, or select '
                                                                         'the port and click Read.',
 '{v0}: 보드가 답하지 않아요. 이 펌웨어가 아직 없거나, 다른 프로그램이 포트를 쓰고 있어요. 아래에서 펌웨어를 설치할 수 있어요.': '{v0}: No board response. Firmware may '
                                                                                'be missing or another app may be '
                                                                                'using this port. You can install '
                                                                                'firmware below.',
 '다시 읽지 못했어요: {v0}': 'Could not read again: {v0}',
 '보드를 읽는 중…': 'Reading board…',
 '{v0} · 펌웨어 {v1} · 읽기 완료': '{v0} · Firmware {v1} · Read complete',
 '연결됨 · 보드 주소 {v0}  ← PC 앱과 휴대폰 앱에 이 주소를 넣으세요': 'Connected · Board address {v0} ← Use this in the PC and phone apps',
 "'{v0}'에 연결 중이거나 연결 실패 · 이름과 비밀번호를 확인하세요": "Connecting to '{v0}' or connection failed · Check the name and password",
 '저장된 공유기가 없어요. 휴대폰을 보드 Wi-Fi에 바로 연결해 쓸 수도 있어요.': 'No router saved. You can connect your phone directly to board '
                                                  'Wi-Fi.',
 '지금은 {v0} · 보드의 USB와 COM 케이블을 모두 뺐다 꽂으면 저장한 모드로 바뀌어요.': 'Currently {v0} · Unplug both USB and COM cables, then '
                                                         'reconnect to use the saved mode.',
 '소리가 한쪽만 나거나 안 나면 바꿔 보세요. 저장한 뒤 보드의 USB와 COM 케이블을 모두 뺐다 꽂으면 적용돼요.': 'Try another mode if audio is missing in either '
                                                                     'direction. After saving, unplug both USB and COM '
                                                                     'cables and reconnect.',
 '확인 안 됨': 'Not checked',
 '이 프로그램에 든 것': 'Bundled',
 '설치할 펌웨어: {v0} ({v1}) · 지금 보드: {v2}': 'Install: {v0} ({v1}) · Board: {v2}',
 '설치할 펌웨어: 없음 · {v0} · 지금 보드: {v1}': 'Install: None · {v0} · Board: {v1}',
 '보드 Wi-Fi 비밀번호를 복사했어요.': 'Board Wi-Fi password copied.',
 '저장하지 못했어요: {v0}': 'Could not save: {v0}',
 '보드 Wi-Fi 비밀번호: {v0}': 'Board Wi-Fi password: {v0}',
 '보드 Wi-Fi 비밀번호가 그대로예요. 칸에서 고친 뒤 저장하세요.': 'Password unchanged. Edit the field before saving.',
 '보드 Wi-Fi 비밀번호를 "{v0}"로 바꿀까요?\n보드 Wi-Fi에 바로 연결해 쓰던 휴대폰과 PC는 새 비밀번호로 다시 연결해야 해요.': 'Change the board Wi-Fi password to '
                                                                                   '"{v0}"?\n'
                                                                                   'Devices connected directly to '
                                                                                   'board Wi-Fi will need to reconnect '
                                                                                   'with the new password.',
 '\n\n10자보다 짧으면 근처에서 추측하기 쉬워요.': '\n\nPasswords shorter than 10 characters are easier to guess.',
 '보드 Wi-Fi 비밀번호': 'Board Wi-Fi password',
 '비밀번호를 저장하는 중…': 'Saving password…',
 '비밀번호를 저장했어요. 보드 Wi-Fi에 연결했던 기기는 새 비밀번호로 다시 연결하세요.': 'Password saved. Reconnect devices on board Wi-Fi using the new '
                                                      'password.',
 '무작위 비밀번호': 'Random password',
 '보드 Wi-Fi 비밀번호를 무작위로 새로 만들까요?\n보드 Wi-Fi에 바로 연결해 쓰던 휴대폰과 PC는 새 비밀번호로 다시 연결해야 해요.': 'Generate a new random board Wi-Fi '
                                                                                   'password?\n'
                                                                                   'Devices connected directly to '
                                                                                   'board Wi-Fi will need to reconnect '
                                                                                   'with the new password.',
 '새 비밀번호를 만드는 중…': 'Generating password…',
 '새 비밀번호를 저장했어요. 보드 Wi-Fi에 연결했던 기기는 다시 연결하세요.': 'New password saved. Reconnect devices on board Wi-Fi.',
 '공유기 이름을 넣으세요.': 'Enter the router Wi-Fi name.',
 '공유기 이름이 너무 길어요 (32바이트까지).': 'Router Wi-Fi name is too long (maximum 32 bytes).',
 '공유기 비밀번호는 8~63자예요.': 'Router password must be 8–63 characters.',
 '공유기 Wi-Fi': 'Router Wi-Fi',
 "'{v0}'는 비밀번호 없는 Wi-Fi인가요?": "Is '{v0}' an open Wi-Fi network without a password?",
 '공유기 비밀번호를 넣고 저장하세요. 보드는 저장된 비밀번호를 보여 주지 않아서 바꿀 때마다 넣어야 해요.': 'Enter the router password and save. The board does not '
                                                               'show saved passwords, so enter it each time you change '
                                                               'these settings.',
 "'{v0}'를 저장했어요. 연결되면 보드 주소가 나타나요.": "Saved '{v0}'. The board address will appear once connected.",
 '공유기 설정을 저장하는 중…': 'Saving router settings…',
 '저장된 공유기를 지울까요? 그다음엔 보드 Wi-Fi에 바로 연결해서 써야 해요.': 'Forget the saved router? You will then need to connect directly to '
                                                 'board Wi-Fi.',
 '공유기 설정을 지우는 중…': 'Forgetting router…',
 '공유기 설정을 지웠어요.': 'Router settings cleared.',
 'USB 모드를 저장하는 중…': 'Saving USB mode…',
 'USB 모드를 저장했어요. 보드의 USB와 COM 케이블을 모두 뺐다 꽂으면 적용돼요.': 'USB mode saved. Unplug both USB and COM cables, then reconnect '
                                                     'to apply it.',
 '펌웨어 폴더 (manifest.json이 있는 곳)': 'Firmware folder (containing manifest.json)',
 '이 포트는 보드의 오디오 USB 쪽이에요. COM(USB-시리얼) 단자를 연결해서 고르세요.': "This is the board's audio USB port. Connect and select the "
                                                        'COM (USB-serial) port instead.',
 '{v0} 보드에 펌웨어 {v1}를 설치할까요?\n\n설치하는 1분쯤 동안 소리가 끊기고, 끝나면 보드가 다시 시작해요. 그동안 케이블을 빼지 마세요.': 'Install firmware {v1} on '
                                                                                        '{v0}?\n'
                                                                                        '\n'
                                                                                        'Audio will stop for about a '
                                                                                        'minute and the board will '
                                                                                        'restart. Keep the cables '
                                                                                        'connected during '
                                                                                        'installation.',
 '\n\n설정도 지워요: 보드 Wi-Fi 비밀번호가 새로 만들어지고 공유기 설정과 USB 모드가 없어져요.': '\n'
                                                               '\n'
                                                               'Settings will also be erased: a new board Wi-Fi '
                                                               'password will be generated, and router settings and '
                                                               'USB mode will be reset.',
 '설치하지 못했어요: {v0}\n다시 해 보고, 그래도 안 되면 BOOT를 누른 채 RESET을 눌렀다 떼고 다시 설치를 누르세요.': 'Installation failed: {v0}\n'
                                                                             'Try again. If it still fails, hold BOOT, '
                                                                             'press and release RESET, then click '
                                                                             'Install again.',
 '설치 끝 · 펌웨어 {v0}가 돌고 있어요.': 'Installed · Firmware {v0} is running.',
 '설치는 확인까지 끝났는데 보드가 아직 답하지 않아요. RESET 버튼을 누르거나 케이블을 다시 꽂고 읽기를 누르세요.': 'Firmware was installed and verified, but the '
                                                                      'board has not responded yet. Press RESET or '
                                                                      'reconnect the cable, then click Read.',
 '펌웨어를 설치하는 중…': 'Installing firmware…',
 '보드 응답이 너무 큽니다': 'Board response is too large',
 'ESP32 헤드셋 상태 응답이 아닙니다': 'Not an ESP32 headset status response',
 '올바른 보드 IPv4 주소를 입력하세요': 'Enter a valid board IPv4 address',
 'USB 모드 · 확인 불가 (보드 주소·연결 확인)': 'USB mode · Unavailable (check address and connection)',
 'Apple · 아이폰 호환': 'Apple · iPhone compatible',
 '현재 USB 모드 · ': 'Current USB mode · ',
 '알 수 없음 (펌웨어 확인)': 'Unknown (check firmware)',
 '연결 준비 중': 'Preparing connection',
 'AAC 처리 실패: {v0}': 'AAC processing failed: {v0}',
 'Windows 오디오 초기화 실패: 0x{v0:08X}': 'Windows audio initialization failed: 0x{v0:08X}',
 '보드 응답 대기': 'Waiting for board',
 '양방향 연결됨 · 기기 소리는 선택한 출력으로 재생': 'Connected both ways · Device audio plays on the selected output',
 '보드 응답 없음: IP·같은 네트워크·양방향 펌웨어를 확인하세요.': 'No board response: check IP, shared network and duplex firmware.',
 '보드 응답이 지연되고 있어요.': 'Board response is delayed.',
 '연결 종료 · USB 마이크는 무음': 'Disconnected · USB microphone is silent',
 '지원하지 않는 음질 설정이에요.': 'Unsupported audio quality settings.',
 '이 샘플레이트에서 지원하지 않는 AAC 비트레이트예요.': 'Unsupported AAC bitrate for this sample rate.',
 '원음 PCM · AAC 끔': 'Original PCM · AAC off',
 'AAC에 쓸 ffmpeg를 찾지 못했어요 (앱 폴더의 ffmpeg/ffmpeg.exe).': 'FFmpeg for AAC was not found (ffmpeg/ffmpeg.exe in the app '
                                                      'folder).',
 'AAC 전달 실패: {v0}': 'AAC transfer failed: {v0}',
 'AAC 복원 실패: {v0}': 'AAC decoding failed: {v0}',
 '종료 코드 {v0}': 'Exit code {v0}',
 'AAC {v0} 프로세스가 멈췄어요: {v1}': 'AAC {v0} process stopped: {v1}',
 'AAC 인코더에 쓰지 못했어요: {v0}': 'Could not write to AAC encoder: {v0}',
 '입력': 'Input',
 '출력': 'Output',
 '{v0} 장치의 지원 오디오 형식을 찾지 못했어요: {v1}. 다른 드라이버 항목을 선택해 주세요.': 'No supported audio format for {v0} device: {v1}. Select '
                                                            'another driver entry.',
 '앞뒤 공백은 빼 주세요. 휴대폰에서 칠 때 헷갈려요.': 'Remove leading or trailing spaces to avoid confusion when typing on a phone.',
 '8~63자로 정하세요.': 'Use 8–63 characters.',
 '영문, 숫자, 기호만 쓸 수 있어요 (한글·이모지는 Wi-Fi 비밀번호에 못 써요).': 'Use ASCII letters, numbers and symbols only (no Korean characters '
                                                    'or emoji).',
 '보드가 답하지 않아요': 'Board did not respond',
 '이 펌웨어의 보드가 아니에요': 'Not a board running this firmware',
 '이 보드용 펌웨어가 아니에요 (manifest.json)': 'Firmware is not for this board (manifest.json)',
 '{v0} 파일이 손상됐어요 (SHA-256 불일치)': '{v0} is damaged (SHA-256 mismatch)',
 'manifest.json에 bootloader, partition-table, app이 모두 있어야 해요': 'manifest.json must include bootloader, partition-table '
                                                               'and app',
 '다운로드 모드로 들어가는 중': 'Entering download mode',
 '파티션 표에 설정(NVS) 영역이 없어요': 'No settings (NVS) region in partition table',
 '{v0} 쓰는 중 (0x{v1:x})': 'Writing {v0} (0x{v1:x})',
 '확인 끝, 새 펌웨어로 시작하는 중': 'Verified; starting new firmware',
 '설정 저장': 'Save settings'}
