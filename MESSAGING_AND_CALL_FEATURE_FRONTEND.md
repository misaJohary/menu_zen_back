# Messaging & Call Feature — Flutter Frontend Plan

Companion to [MESSAGING_AND_CALL_FEATURE_PLAN.md](MESSAGING_AND_CALL_FEATURE_PLAN.md). Targets the
existing Melos monorepo at `menu_zen_restaurant/` (apps + packages).

## Project layout reminder

```
menu_zen_restaurant/
├── apps/menu_zen_tablet/           ← presentation (BLoC/Cubit, screens, widgets)
├── apps/menu_zen_mobile/
└── packages/
    ├── domain/                     ← entities + repository interfaces
    ├── data/                       ← models + retrofit REST + repository impls + DI
    └── design_system/              ← theme + shared widgets
```

Stack: `flutter_bloc`, `get_it` + `injectable`, `dio` + `retrofit`,
`web_socket_channel` (already in pubspec), `auto_route`, `json_serializable`.

---

## Step 1 — Add Flutter dependencies

In `apps/menu_zen_tablet/pubspec.yaml` and `apps/menu_zen_mobile/pubspec.yaml`:

```yaml
dependencies:
  flutter_webrtc: ^0.11.7         # WebRTC PeerConnection + audio routing (audio-only, no camera)
  permission_handler: ^11.3.1     # microphone runtime permission
  flutter_callkit_incoming: ^2.5.1 # native incoming-call UI (CallKit on iOS, ConnectionService on Android)
  file_picker: ^8.1.2             # attachments
  emoji_picker_flutter: ^3.1.0    # optional but expected
  uuid: ^4.5.1
  rxdart: ^0.28.0                 # for combining streams in WS service
```

In `packages/data/pubspec.yaml`:

```yaml
dependencies:
  web_socket_channel: ^3.0.3      # already in tablet, also needed in data
  rxdart: ^0.28.0
```

Run `melos bootstrap` after editing.

### Native config

- **iOS** (`ios/Runner/Info.plist`):
  ```xml
  <key>NSMicrophoneUsageDescription</key><string>Used for voice calls</string>
  <key>UIBackgroundModes</key>
  <array><string>audio</string><string>voip</string></array>
  ```
- **Android** (`AndroidManifest.xml`):
  ```xml
  <uses-permission android:name="android.permission.INTERNET"/>
  <uses-permission android:name="android.permission.RECORD_AUDIO"/>
  <uses-permission android:name="android.permission.MODIFY_AUDIO_SETTINGS"/>
  <uses-permission android:name="android.permission.BLUETOOTH"/>
  <uses-permission android:name="android.permission.FOREGROUND_SERVICE"/>
  <uses-permission android:name="android.permission.FOREGROUND_SERVICE_MICROPHONE"/>
  <uses-permission android:name="android.permission.POST_NOTIFICATIONS"/>
  ```
  `minSdkVersion` ≥ 23.

---

## Step 2 — Domain layer (`packages/domain/lib/`)

### 2a. Enums

`entities/messaging/conversation_type.dart`, `message_type.dart`,
`call_status.dart`, `call_participant_state.dart` — mirror the backend enums
(`direct/group`, `text/image/file/system/call_event`,
`ringing/active/ended/missed/declined`, `invited/joined/left/declined`).

### 2b. Entities

Pure Dart classes, no JSON, extend `Equatable`:

| File | Purpose |
| ---- | ------- |
| `conversation_entity.dart`             | id, type, name?, restaurantId, createdById, createdAt, updatedAt, participants, lastMessage?, unreadCount |
| `participant_entity.dart`              | userId, username, fullName?, joinedAt, lastReadMessageId?, isAdmin |
| `message_entity.dart`                  | id, conversationId, senderId, senderUsername?, type, content?, attachmentUrl?, attachmentName?, replyToId?, createdAt, editedAt?, deletedAt? |
| `call_entity.dart`                     | id, conversationId, status, startedById, startedAt?, endedAt?, participants |
| `call_participant_entity.dart`         | userId, username?, state, joinedAt?, leftAt? |

### 2c. Repository interfaces (`repositories/`)

```dart
abstract class ConversationsRepository {
  Future<List<ConversationEntity>> list();
  Future<ConversationEntity> getById(int id);
  Future<ConversationEntity> createDirect(int otherUserId);
  Future<ConversationEntity> createGroup({required String name, required List<int> participantIds});
  Future<ConversationEntity> rename(int id, String name);
  Future<void> addParticipants(int id, List<int> userIds);
  Future<void> removeParticipant(int id, int userId);
  Future<void> markRead(int id, int lastMessageId);
}

abstract class MessagesRepository {
  Future<List<MessageEntity>> history(int conversationId, {int? beforeId, int limit = 50});
  Future<MessageEntity> send(int conversationId, MessageDraft draft);
  Future<MessageEntity> edit(int messageId, String content);
  Future<void> delete(int messageId);
  Future<String> uploadAttachment(File file);             // returns url
}

abstract class CallsRepository {
  Future<CallEntity> start(int conversationId);
  Future<CallEntity> accept(int callId);
  Future<CallEntity> decline(int callId);
  Future<CallEntity> leave(int callId);
  Future<List<CallEntity>> historyFor(int conversationId);
}

abstract class ChatRealtimeRepository {
  /// Single hot stream of decoded server events.
  Stream<ChatRealtimeEvent> get events;

  Future<void> connect();
  Future<void> disconnect();

  void sendTypingStart(int conversationId);
  void sendTypingStop(int conversationId);
  void sendSignal({required int callId, required int toUserId, required SignalKind kind, required Map<String, dynamic> payload});
}
```

`ChatRealtimeEvent` is a `sealed class` with subtypes `MessageNew`,
`MessageEdited`, `MessageDeleted`, `MessageRead`, `ConversationCreated`,
`ConversationUpdated`, `MemberAdded`, `MemberRemoved`, `PresenceOnline`,
`PresenceOffline`, `TypingStart`, `TypingStop`, `CallIncoming`, `CallAccepted`,
`CallDeclined`, `CallEnded`, `CallParticipantJoined`, `CallParticipantLeft`,
`CallSignal`. Exhaustive `switch` consumes it cleanly in BLoCs.

### 2d. Params

- `MessageDraft({type, content?, attachmentUrl?, attachmentName?, replyToId?})`
- `SendCallSignalParams`, `StartCallParams`, etc. — mirror backend `*Request` schemas.

### 2e. Use cases

One class per action under `usecases/messaging/` and `usecases/calls/`. Use the
project's `UseCase<Result, Params>` base + `dartz.Either<Failure, T>`. Examples:

- `GetConversationsUseCase`, `GetMessagesUseCase`, `SendMessageUseCase`,
  `MarkReadUseCase`, `UploadAttachmentUseCase`
- `StartCallUseCase`, `AcceptCallUseCase`, `DeclineCallUseCase`, `LeaveCallUseCase`
- `ConnectChatRealtimeUseCase`, `WatchChatEventsUseCase`, `SendSignalUseCase`

---

## Step 3 — Data layer (`packages/data/lib/`)

### 3a. Models (`models/messaging/`, `models/calls/`)

For each entity create a `*_model.dart` with `@JsonSerializable(fieldRename: FieldRename.snake)`
and `toEntity()` mapping. Naming follows the existing pattern (e.g. `category_model.dart`).

```dart
@JsonSerializable(fieldRename: FieldRename.snake)
class MessageModel {
  final int id;
  final int conversationId;
  final int? senderId;
  final String? senderUsername;
  final String type;
  final String? content;
  final String? attachmentUrl;
  final String? attachmentName;
  final int? replyToId;
  final DateTime createdAt;
  final DateTime? editedAt;
  final DateTime? deletedAt;

  MessageModel({...});
  factory MessageModel.fromJson(Map<String, dynamic> json) => _$MessageModelFromJson(json);
  Map<String, dynamic> toJson() => _$MessageModelToJson(this);

  MessageEntity toEntity() => MessageEntity(...);
}
```

Run `dart run build_runner build --delete-conflicting-outputs` inside
`packages/data` after adding files.

### 3b. REST client additions (`http/rest_client.dart`)

Append to the existing retrofit `RestClient` abstract class:

```dart
@GET('/conversations')
Future<List<ConversationModel>> getConversations();

@GET('/conversations/{id}')
Future<ConversationModel> getConversation(@Path('id') int id);

@POST('/conversations')
Future<ConversationModel> createConversation(@Body() CreateConversationModel body);

@PATCH('/conversations/{id}')
Future<ConversationModel> updateConversation(@Path('id') int id, @Body() Map<String, dynamic> body);

@POST('/conversations/{id}/participants')
Future<void> addParticipants(@Path('id') int id, @Body() Map<String, dynamic> body);

@DELETE('/conversations/{id}/participants/{userId}')
Future<void> removeParticipant(@Path('id') int id, @Path('userId') int userId);

@GET('/conversations/{id}/messages')
Future<List<MessageModel>> getMessages(
  @Path('id') int id,
  @Query('before_id') int? beforeId,
  @Query('limit') int limit,
);

@POST('/conversations/{id}/messages')
Future<MessageModel> sendMessage(@Path('id') int id, @Body() SendMessageModel body);

@PATCH('/messages/{id}')
Future<MessageModel> editMessage(@Path('id') int id, @Body() Map<String, dynamic> body);

@DELETE('/messages/{id}')
Future<void> deleteMessage(@Path('id') int id);

@POST('/conversations/{id}/read')
Future<void> markRead(@Path('id') int id, @Body() Map<String, dynamic> body);

@POST('/messages/upload')
@MultiPart()
Future<Map<String, dynamic>> uploadChatAttachment(@Part() File file);

@POST('/calls')
Future<CallModel> startCall(@Body() StartCallModel body);

@POST('/calls/{id}/accept')
Future<CallModel> acceptCall(@Path('id') int id);

@POST('/calls/{id}/decline')
Future<CallModel> declineCall(@Path('id') int id);

@POST('/calls/{id}/leave')
Future<CallModel> leaveCall(@Path('id') int id);

@GET('/conversations/{id}/calls')
Future<List<CallModel>> callHistory(@Path('id') int id);
```

Re-run build_runner.

### 3c. ChatSocketService (`services/chat_socket_service.dart`)

The single most important piece. Handles connect, auth, reconnect with
exponential backoff, heartbeat, encode/decode, and exposes a broadcast stream
of `ChatRealtimeEvent`.

```dart
@lazySingleton
class ChatSocketService {
  ChatSocketService(this._tokenStore, this._config);

  final TokenStore _tokenStore;
  final AppConfig _config;

  WebSocketChannel? _channel;
  final _events = StreamController<ChatRealtimeEvent>.broadcast();
  Timer? _heartbeat;
  Timer? _reconnect;
  int _backoffSeconds = 1;
  bool _intentionallyClosed = false;

  Stream<ChatRealtimeEvent> get events => _events.stream;
  bool get isConnected => _channel != null;

  Future<void> connect() async {
    _intentionallyClosed = false;
    final token = await _tokenStore.read();
    final uri = Uri.parse('${_config.wsBaseUrl}/ws/chat?token=$token');
    _channel = WebSocketChannel.connect(uri);

    _channel!.stream.listen(
      _onMessage,
      onError: (e) => _scheduleReconnect(),
      onDone: () { if (!_intentionallyClosed) _scheduleReconnect(); },
    );

    _heartbeat = Timer.periodic(const Duration(seconds: 25),
        (_) => _send({'type': 'ping'}));
    _backoffSeconds = 1;
  }

  Future<void> disconnect() async {
    _intentionallyClosed = true;
    _heartbeat?.cancel();
    _reconnect?.cancel();
    await _channel?.sink.close();
    _channel = null;
  }

  void sendTypingStart(int conversationId) =>
      _send({'type': 'typing.start', 'data': {'conversation_id': conversationId}});
  void sendTypingStop(int conversationId) =>
      _send({'type': 'typing.stop', 'data': {'conversation_id': conversationId}});

  void sendSignal({required int callId, required int toUserId, required SignalKind kind, required Map<String, dynamic> payload}) {
    _send({
      'type': 'signal',
      'data': {
        'call_id': callId,
        'to_user_id': toUserId,
        'kind': kind.wire,
        'payload': payload,
      }
    });
  }

  void _send(Map<String, dynamic> payload) {
    if (_channel == null) return;
    _channel!.sink.add(jsonEncode(payload));
  }

  void _onMessage(dynamic raw) {
    try {
      final json = jsonDecode(raw as String) as Map<String, dynamic>;
      final type = json['type'] as String?;
      if (type == 'pong') return;
      final event = ChatRealtimeEvent.fromWire(type!, json['data'] as Map<String, dynamic>);
      if (event != null) _events.add(event);
    } catch (e, s) {
      developer.log('ChatSocket decode error', error: e, stackTrace: s);
    }
  }

  void _scheduleReconnect() {
    _channel = null;
    _heartbeat?.cancel();
    _reconnect = Timer(Duration(seconds: _backoffSeconds), connect);
    _backoffSeconds = (_backoffSeconds * 2).clamp(1, 30);
  }
}
```

`ChatRealtimeEvent.fromWire` is a factory that switches on the server's `type`
string and constructs the matching subclass.

### 3d. Repository implementations

`conversations_repository_impl.dart`, `messages_repository_impl.dart`,
`calls_repository_impl.dart` — wrap `RestClient` calls and map model→entity.
`chat_realtime_repository_impl.dart` — delegate to `ChatSocketService`.

### 3e. DI registration (`packages/data/lib/di/`)

Already uses `injectable`. Add `@LazySingleton(as: ConversationsRepository)`
etc. on each impl. After edits run injectable codegen.

---

## Step 4 — WebRTC service (`packages/data/lib/services/webrtc_service.dart`)

Manages `RTCPeerConnection` lifecycle per active call. **Audio-only** — no
video tracks created or received. One service, one peer connection (1:1 calls)
— for group calls we maintain a `Map<int, RTCPeerConnection>` keyed by remote
user id (mesh topology, fine up to ~5 participants).

```dart
@injectable
class WebRtcService {
  WebRtcService(this._socket);

  final ChatSocketService _socket;
  final Map<int, RTCPeerConnection> _peers = {};
  MediaStream? _localStream;

  final _remoteStreams = StreamController<({int userId, MediaStream stream})>.broadcast();
  Stream<({int userId, MediaStream stream})> get remoteStreams => _remoteStreams.stream;

  MediaStream? get localStream => _localStream;

  static const _config = {
    'iceServers': [
      {'urls': 'stun:stun.l.google.com:19302'},
      // TURN added via env var when available
    ],
  };

  Future<void> initLocalMedia() async {
    _localStream = await navigator.mediaDevices.getUserMedia({
      'audio': true,
      'video': false,
    });
  }

  /// Caller side — create offer and send via socket.
  Future<void> initiate({required int callId, required int remoteUserId}) async {
    final pc = await _newPeer(callId, remoteUserId);
    final offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    _socket.sendSignal(
      callId: callId,
      toUserId: remoteUserId,
      kind: SignalKind.offer,
      payload: offer.toMap(),
    );
  }

  /// Callee side — apply offer, answer.
  Future<void> handleOffer({required int callId, required int fromUserId, required Map<String, dynamic> sdp}) async {
    final pc = await _newPeer(callId, fromUserId);
    await pc.setRemoteDescription(RTCSessionDescription(sdp['sdp'], sdp['type']));
    final answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    _socket.sendSignal(
      callId: callId,
      toUserId: fromUserId,
      kind: SignalKind.answer,
      payload: answer.toMap(),
    );
  }

  Future<void> handleAnswer({required int fromUserId, required Map<String, dynamic> sdp}) async {
    await _peers[fromUserId]?.setRemoteDescription(RTCSessionDescription(sdp['sdp'], sdp['type']));
  }

  Future<void> handleIce({required int fromUserId, required Map<String, dynamic> candidate}) async {
    await _peers[fromUserId]?.addCandidate(RTCIceCandidate(
      candidate['candidate'],
      candidate['sdpMid'],
      candidate['sdpMLineIndex'],
    ));
  }

  Future<RTCPeerConnection> _newPeer(int callId, int remoteUserId) async {
    final pc = await createPeerConnection(_config);
    _localStream?.getTracks().forEach((t) => pc.addTrack(t, _localStream!));

    pc.onIceCandidate = (c) {
      _socket.sendSignal(
        callId: callId,
        toUserId: remoteUserId,
        kind: SignalKind.ice,
        payload: c.toMap(),
      );
    };
    pc.onTrack = (e) {
      if (e.streams.isNotEmpty) {
        _remoteStreams.add((userId: remoteUserId, stream: e.streams.first));
      }
    };
    _peers[remoteUserId] = pc;
    return pc;
  }

  Future<void> toggleMute() async {
    final track = _localStream?.getAudioTracks().firstOrNull;
    if (track != null) track.enabled = !track.enabled;
  }

  Future<void> setSpeakerphone(bool on) async {
    await Helper.setSpeakerphoneOn(on);
  }

  Future<void> hangUp() async {
    for (final pc in _peers.values) { await pc.close(); }
    _peers.clear();
    await _localStream?.dispose();
    _localStream = null;
  }
}
```

This service is **not** a repository — it's a low-level facade the call BLoC
talks to directly.

---

## Step 5 — Presentation: app-wide chat realtime hub

A long-lived Cubit kicked off at app startup (after login) that owns the WS
connection and re-emits events.

`apps/menu_zen_tablet/lib/features/presentations/controllers/chat/chat_realtime_cubit.dart`

```dart
@injectable
class ChatRealtimeCubit extends Cubit<ChatRealtimeState> {
  ChatRealtimeCubit(this._connect, this._watch) : super(const ChatRealtimeIdle()) {
    _watch().listen(_onEvent);
  }

  final ConnectChatRealtimeUseCase _connect;
  final WatchChatEventsUseCase _watch;

  Future<void> start() async {
    emit(const ChatRealtimeConnecting());
    final r = await _connect(NoParams());
    r.fold(
      (f) => emit(ChatRealtimeError(f.message)),
      (_) => emit(const ChatRealtimeConnected()),
    );
  }

  void _onEvent(ChatRealtimeEvent e) {
    // route to listening BLoCs via a stream the rest of the app subscribes to,
    // OR use BlocListener<ChatRealtimeCubit, _> with a broadcast events field.
    _events.add(e);
  }

  final _events = StreamController<ChatRealtimeEvent>.broadcast();
  Stream<ChatRealtimeEvent> get events => _events.stream;
}
```

Provided once at app root via `BlocProvider.value(value: getIt<ChatRealtimeCubit>())`
in `app.dart`, started after auth is confirmed.

---

## Step 6 — Presentation: Conversations list (Messenger-style)

`controllers/conversations/conversations_cubit.dart`

States: `ConversationsLoading | ConversationsLoaded(items, unread) | ConversationsError`.

The cubit `listen()`s to `ChatRealtimeCubit.events` (passed in constructor) and
on `MessageNew`/`ConversationUpdated`/`ConversationCreated` mutates the loaded
list in place (move conversation to top, increment unread, replace
`lastMessage`).

### UI spec — modeled on Facebook Messenger's "Chats" tab

Screen: `screens/chat/conversations_screen.dart`

**Layout (top → bottom):**

1. **Header row** — large bold title `Chats` (28sp, weight 700) on the left,
   compact circular icon button on the right (new-message pencil icon).
   No `AppBar` elevation; flush with the body.
2. **Avatar row** ("Active now") — horizontal `ListView` of online colleagues:
   56dp circular avatar with a 14dp green dot (`#31A24C`) bottom-right, name
   label below truncated to first name, 12sp. Hidden when no one is online.
3. **Search pill** — full-width rounded rectangle (radius 22), neutral gray
   background (`surfaceContainerHighest`), leading magnifier icon + "Search"
   placeholder. Tap navigates to `ChatSearchScreen`.
4. **Conversation list** — `ListView.builder` of `ConversationTile`. No
   dividers. 8dp vertical padding per row.

**`ConversationTile` anatomy** (Messenger row, ~72dp tall):

```
┌─────────────────────────────────────────────────────┐
│  ●Avatar     Name (bold if unread)        12:34 PM •│
│   56dp       Last message preview…                  │
└─────────────────────────────────────────────────────┘
```

- **Avatar (56×56, circular)** — `cached_network_image` with initials fallback
  (gradient background using a deterministic color derived from `userId`).
  Online dot overlay (12dp, 2dp white border) bottom-right when participant is
  online (from `presence` events). For groups: stacked 2-avatar composition
  (back-left 40dp, front-right 40dp with 2dp white border).
- **Title** (`Name`): 16sp, weight 600 when `unreadCount > 0`, otherwise
  weight 500. Single line, ellipsis.
- **Subtitle** (last message preview): 14sp.
  - Format: `"You: …"` if I'm the sender (1:1) or `"Alice: …"` (group).
  - Plain text for `text` messages, `🖼 Photo` / `📎 File` icons for attachments.
  - Color: `onSurface` at 100% when unread, `onSurfaceVariant` (60%) when read.
  - Append `· 12:34 PM` time and (if read by other side) tiny seen-avatar
    overlapping the right edge (12dp).
- **Trailing column** (right-aligned):
  - Time stamp top (12sp). Today → `12:34 PM`; this week → `Mon`; older → `Apr 12`.
  - When unread > 0: solid Messenger-blue dot (10dp, `#0866FF`) bottom-right
    instead of a count badge (matches current Messenger).
- **Long-press** → bottom sheet: `Mark as unread`, `Mute notifications`,
  `Delete conversation`, `View profile`.
- **Swipe-right** → quick-reply (focuses input on next screen).
- **Swipe-left** → reveal `Archive` action (background `#0866FF`, white icon).

**Empty state** — center illustration (use existing `assets/lotties/`) + "No
chats yet" + outlined button "Send a new message".

**FAB** — none (Messenger uses the header pencil icon instead). Pencil icon →
`NewConversationScreen`.

**`NewConversationScreen`:**
- Sticky search bar at top.
- Section 1: `Recent` (last conversations).
- Section 2: `All staff` — list of users from `/users` filtered by current
  restaurant. Multi-select chips appear in a row above the list when ≥1 is
  selected; CTA "Start chat" (Messenger-blue filled pill) appears at bottom.
- Selecting exactly 1 → creates direct conversation (or returns existing).
- Selecting ≥2 → switches to group form: required `Group name` field above
  the selection.

---

## Step 7 — Presentation: Conversation (chat) screen (Messenger-style)

`controllers/conversation/conversation_bloc.dart` — full BLoC. Events:
`LoadHistory`, `LoadMore`, `MessageReceived`, `Send`, `EditRequested`,
`DeleteRequested`, `MarkAllRead`, `TypingStarted`, `TypingStopped`,
`ReactionToggled`.

State: `ConversationState({status, messages, hasMore, typingUserIds, error?})`.

Wires:
- On open → `LoadHistory(conversationId)` then `MarkAllRead`.
- Subscribe to `ChatRealtimeCubit.events`, filter
  `MessageNew`/`MessageEdited`/`MessageDeleted`/`MessageRead`/
  `TypingStart`/`TypingStop` for this `conversationId`.
- Optimistic send: insert message with `tempId` and a `sending` status,
  replace with the server response on success, mark `failed` on error.
- Pagination: scroll near top → emit `LoadMore` with `beforeId = oldest.id`.

### UI spec — modeled on Facebook Messenger's chat screen

**Top bar** (custom, height 64dp):

```
←   ●Avatar  Name           📞
        (online status)
```

- Back arrow (24dp).
- 36dp circular avatar with online dot.
- Two-line title: top — display name (16sp, weight 600); bottom — small label
  `Active now` (12sp, `onSurfaceVariant`) when online, otherwise
  `Active 5m ago` (computed from `presence` events). For groups: title is
  group name + subtitle `N members`.
- Trailing icon: **phone** only (24dp, hit area 48dp). Tap → `CallCubit.startCall`.
  No camera icon (audio-only).
- Tapping the title row opens `ConversationDetailsScreen` (members, mute,
  rename for groups, search messages, leave group).

**Message list** (`ListView.builder`, reverse: true):

- **Bubble** — rounded 18dp by default, but **smart corner squashing** when
  consecutive messages come from the same sender (Messenger's signature look):
  - Standalone bubble: all 4 corners 18dp.
  - First in run: 18dp except bottom-right (own) / bottom-left (other) → 4dp.
  - Middle in run: 4dp on the inner side, 18dp on the outer.
  - Last in run: 4dp on the inner top corner only.
  Helper: `BorderRadius _runRadius({required bool isOwn, required bool isFirstInRun, required bool isLastInRun})`.
- **Own messages** — right-aligned, Messenger-blue background (`#0866FF`),
  white text (15sp). Max width 75% of screen.
- **Other messages** — left-aligned, neutral surface (`#E4E6EB` light /
  `#3A3B3C` dark), `onSurface` text. 28dp avatar shown only on the **last**
  bubble of a run (left side, aligned to bubble bottom). Avatar slot reserved
  (32dp wide spacer) on the other bubbles to keep alignment.
- **Sender name** (group only) — 12sp `onSurfaceVariant`, shown above the
  first bubble of a run from a non-self sender, indented to bubble's left edge.
- **Reactions** — small overlapping pill below the bubble's bottom-right
  (own) / bottom-left (other), 24dp wide, white background with shadow,
  emoji + count if >1. Tap on a bubble's reaction toggles it.
- **Long-press a bubble** → reaction picker (horizontal row of 6 reactions:
  ❤️ 😆 😮 😢 😡 👍) appears above the bubble in a floating sheet, plus an
  action sheet below: `Reply`, `Forward`, `Copy`, `Edit` (own), `Delete` (own),
  `More`. Use `showModalBottomSheet` with a custom transition that scales
  the bubble into focus and dims the rest (Messenger's selection mode).
- **Reply preview** above the bubble — 2dp left border, 12sp original sender
  name, 13sp truncated original text. Tap → scrolls to original.
- **Image messages** — clipped to 16dp radius, max 240dp tall, aspect
  preserved. Tap → fullscreen viewer with hero animation. No bubble around it.
- **File messages** — pill-style bubble: file icon + filename (15sp) + size
  subtitle (12sp), tap opens via `open_file` package.
- **System messages** (member added/removed, call started/ended) —
  centered, no bubble, gray 13sp text. Examples:
  `Alice started a call`, `Call ended · 2m 14s`.
- **Date separator** — when the gap between two messages crosses a day
  boundary OR exceeds 1 hour, insert a centered 12sp gray label:
  `Today, 12:34 PM`, `Yesterday, 9:00 AM`, `Monday, 14:20`, `Apr 12, 2026`.

**Tail timestamp** — Messenger doesn't show a timestamp under every bubble;
instead, tapping anywhere on a bubble (or the row) reveals the absolute time
inline (animated slide-in from the right, 200ms). Implement via a per-row
`AnimatedAlign` controlled by a selected-message id in state.

**Read receipt** — at the bottom of the **last own message that has been
read** by the recipient(s), render a 14dp avatar of the reader (1:1) or up to
3 small avatars (group). When new messages arrive, the receipt slides down
to the new last-read message.

**Typing indicator** — three animated bouncing dots inside an "other" bubble
shape on the left, 28dp avatar of the typer. For multiple typers, show
"Alice and Bob are typing" above the dots. Animate with a 600ms looping
sequence (`AnimationController` + staggered offsets).

**Input bar** (sticky bottom, padding 8dp + safe area):

```
[+] [🎤?]   [ rounded text field with 😊 ]   [➤]
```

- **Plus button** (32dp circular, Messenger-blue) — collapsed state. Tap
  expands to a horizontal row of attachment shortcuts (camera, gallery, file,
  voice clip, location). Animated width transition (200ms).
- **Voice clip** (`🎤`) — visible when text field is empty; press-and-hold to
  record (using `record` package) and on release upload + send as `file`
  message with audio mime. Out of scope for v1; placeholder slot kept.
- **Text field** — pill (radius 22), `surfaceContainerHighest` background,
  trailing inline emoji button. `maxLines: 5` with auto-grow.
- **Send button** — appears (with a 150ms scale-in animation) only when
  the text field is non-empty or an attachment is staged. Filled circle
  (32dp), Messenger-blue, white paper-plane icon.
- Typing throttle: emit `TypingStarted` on first keystroke, `TypingStopped`
  3s after the last keystroke (debounced) and on send.

**Pull-to-refresh-up** — `LoadMore` is triggered automatically when scrolling
near the top of the reversed list (no manual indicator); a small
`CircularProgressIndicator` (16dp) appears at the very top while paginating.

**Reusable widgets to add under `presentation/widgets/chat/`:**

- `ChatAppBar`
- `MessageBubble` (uses `_runRadius`)
- `MessageRunBuilder` — groups raw messages into runs with `isFirstInRun` /
  `isLastInRun` / `showAvatar` / `showSenderName` flags before rendering.
- `ReactionPickerSheet`
- `MessageActionSheet`
- `TypingDotsBubble`
- `DateSeparator`
- `ReadReceiptRow`
- `ChatInputBar`
- `AttachmentTray`

---

## Step 8 — Presentation: Calls

### 8a. CallCubit

`controllers/call/call_cubit.dart`

```dart
@injectable
class CallCubit extends Cubit<CallState> {
  CallCubit(this._webrtc, this._calls, this._realtime) : super(const CallIdle()) {
    _sub = _realtime.events.listen(_onEvent);
  }

  final WebRtcService _webrtc;
  final CallsRepository _calls;
  final ChatRealtimeCubit _realtime;
  late final StreamSubscription _sub;

  Future<void> startCall(int conversationId) async {
    emit(const CallStarting());
    await _ensureMicPermission();
    await _webrtc.initLocalMedia();
    final call = await _calls.start(conversationId);
    emit(CallActive(call: call, isOutgoing: true));
    // initiate offers to all other participants once they accept (CallParticipantJoined)
  }

  Future<void> acceptIncoming(CallEntity call) async {
    await _ensureMicPermission();
    await _webrtc.initLocalMedia();
    await _calls.accept(call.id);
    emit(CallActive(call: call, isOutgoing: false));
  }

  Future<void> decline(int callId) async { await _calls.decline(callId); emit(const CallIdle()); }
  Future<void> hangUp() async {
    final state = this.state;
    if (state is CallActive) await _calls.leave(state.call.id);
    await _webrtc.hangUp();
    emit(const CallIdle());
  }

  void _onEvent(ChatRealtimeEvent e) async {
    switch (e) {
      case CallIncoming(:final call):
        emit(CallRinging(call: call));     // triggers UI overlay
      case CallSignal(:final fromUserId, :final kind, :final payload, :final callId):
        switch (kind) {
          case SignalKind.offer:  await _webrtc.handleOffer(callId: callId, fromUserId: fromUserId, sdp: payload);
          case SignalKind.answer: await _webrtc.handleAnswer(fromUserId: fromUserId, sdp: payload);
          case SignalKind.ice:    await _webrtc.handleIce(fromUserId: fromUserId, candidate: payload);
        }
      case CallParticipantJoined(:final callId, :final userId):
        if (state is CallActive && (state as CallActive).isOutgoing) {
          await _webrtc.initiate(callId: callId, remoteUserId: userId);
        }
      case CallEnded():
        await _webrtc.hangUp();
        emit(const CallIdle());
      case _: break;
    }
  }

  Future<void> _ensureMicPermission() async {
    final status = await Permission.microphone.request();
    if (!status.isGranted) {
      throw Exception('Microphone permission denied');
    }
  }
}
```

States: `CallIdle | CallRinging(call) | CallStarting | CallActive(call, isOutgoing) | CallError`.

### 8b. Incoming call overlay (Messenger-style)

A root-level `BlocListener<CallCubit, CallState>` in `app.dart`:

- On `CallRinging` → push `IncomingCallScreen` (full screen, ringtone via
  `audioplayers` looping `assets/sounds/ringtone.mp3`) **and** raise a CallKit
  notification via `flutter_callkit_incoming` so the OS shows native UI even
  if the app is backgrounded.
- On `CallActive` → replace with `InCallScreen` (use
  `Navigator.pushReplacement`).
- On `CallIdle` → pop both.

#### `IncomingCallScreen` UI

Full-screen, dark gradient background (top `#0866FF` → bottom `#0A4FB8`,
matching Messenger's voice-call entry screen). Status bar text in light mode.

- **Top center** (top safe area + 32dp): label `Incoming Messenger Audio` in
  white at 14sp, weight 500. Below it, caller name in white 28sp weight 600,
  then `voice calling…` 16sp white at 80% opacity.
- **Middle**: 144dp circular avatar (group: stacked avatars), with a soft
  white "halo" pulse animation (scale 1.0 → 1.15 → 1.0, 1.6s loop) using a
  decorated container with `BoxShadow` blur 40 spread 0.
- **Bottom action row** (bottom safe area + 56dp), two large 72dp circular
  buttons separated by 80dp:
  - **Decline** (left) — red `#E41E3F`, white phone-down icon, label
    `Decline` (white, 13sp) below.
  - **Accept** (right) — green `#42B72A`, white phone icon, label
    `Accept` below.
- Slide both buttons up 8dp on press (`AnimatedScale` + opacity feedback).
- Optional `Message` quick-reply chip above the action row (Messenger's
  "Reply with a message"): pill button → opens a small text-entry sheet that
  declines the call and sends the typed text into the conversation. Backlog
  for v1.

#### `InCallScreen` UI

Audio-only — no video surfaces. `flutter_webrtc` plays remote audio tracks
automatically once attached, so no `RTCVideoView` is needed.

Background: same dark gradient as `IncomingCallScreen` (visual continuity).

- **Top bar** (transparent, white content):
  - Leading: chevron-down (24dp) — minimizes the call to a draggable floating
    pill via `Overlay` (Messenger's "minimized call bubble"). The bubble shows
    the avatar + a small mic-muted indicator and tapping it returns to the
    full screen.
  - Center: small group icon (or single avatar) 24dp + name (16sp white).
  - Trailing: 3-dot overflow → `Add people`, `Switch to chat`.
- **Hero block** (vertically centered):
  - 168dp circular avatar (1:1) or 3-avatar grid (group, max 9, then `+N`).
  - Below avatar: caller name (24sp weight 600 white).
  - Below name: state line (15sp white 80%) — `Calling…`,
    `Ringing…`, then live timer `02:14` once `CallActive` and the first remote
    stream arrived (drive with a `Ticker` started in
    `WebRtcService.remoteStreams` first event).
  - Speaking indicator: subtle white halo grows around the avatar of the
    currently-speaking participant (using
    `RTCPeerConnection.getStats()` audio level OR the simpler
    `flutter_webrtc` audio-level callback if available; backlog if costly).
- **Bottom action row** (3 round buttons, 64dp, evenly spaced, 32dp from
  bottom safe area):
  - **Mute** — toggle. Idle: white-translucent (`Color.fromRGBO(255,255,255,0.18)`)
    bg with white mic icon. Active (muted): solid white bg with `#0866FF`
    mic-off icon. 12sp `Mute` / `Muted` label below.
  - **Speaker** — toggle (calls `WebRtcService.setSpeakerphone`). Same
    idle/active pattern. Labels: `Speaker` / `Speaker on`.
  - **End call** — red filled circle `#E41E3F`, white phone-down icon, no
    secondary label needed (or `End`).
- Tapping anywhere on the empty middle area toggles the visibility of the
  action row (Messenger hides controls after 5s of inactivity in calls; mirror
  with an `AnimatedOpacity`).

**Group call grid** — when ≥3 participants, replace the centered avatar with
a vertically-centered grid:
- 2 participants → side-by-side 144dp avatars
- 3–4 → 2×2 grid, 120dp each
- 5–6 → 3×2 grid, 100dp each
- ≥7 → 3×3 grid with overflow `+N` tile.
Each tile shows the participant's avatar + name + a 12dp mic-muted icon when
their audio track is disabled (we can detect this only for the local user
unless the backend forwards mute events; backlog).

---

## Step 9 — Routing (`auto_route`)

Add to the router config (see existing `config/router.dart` or similar):

```dart
AutoRoute(page: ConversationsRoute.page, path: '/chat'),
AutoRoute(page: ConversationRoute.page, path: '/chat/:id'),
AutoRoute(page: NewConversationRoute.page, path: '/chat/new'),
AutoRoute(page: IncomingCallRoute.page, path: '/call/incoming', fullscreenDialog: true),
AutoRoute(page: InCallRoute.page, path: '/call/active', fullscreenDialog: true),
```

Run `dart run build_runner build` after adding annotated pages.

---

## Step 10 — Push notifications for offline call delivery (optional, mobile only)

WebSocket-only delivery means the device must be online to receive a call. For
the mobile app, register an FCM token (`firebase_messaging`) on login and have
the backend send a data-only push that triggers a background isolate to launch
`flutter_callkit_incoming`. Out of scope of the initial cut — flag it in the
backlog.

---

## Step 11 — Wiring into app startup

In `app.dart`:

1. After successful login → `getIt<ChatRealtimeCubit>().start()`.
2. On logout → `chatRealtimeCubit.disconnect()` and clear any in-memory chat state.
3. Provide `ChatRealtimeCubit` and `CallCubit` at the root via `MultiBlocProvider`.
4. Add `BlocListener<CallCubit, CallState>` at root for incoming-call routing.

---

## Step 12 — Design system additions (`packages/design_system/`)

Reusable bits that don't depend on entities, themed to match Facebook
Messenger:

### Tokens (`design_system/lib/tokens/messenger_tokens.dart`)

```dart
class MessengerColors {
  // Brand
  static const primaryBlue   = Color(0xFF0866FF); // own bubble, primary CTA
  static const primaryBlueDark = Color(0xFF0A4FB8); // gradient end, pressed

  // Bubbles
  static const bubbleOtherLight = Color(0xFFE4E6EB);
  static const bubbleOtherDark  = Color(0xFF3A3B3C);

  // Status
  static const onlineGreen   = Color(0xFF31A24C);
  static const acceptGreen   = Color(0xFF42B72A);
  static const declineRed    = Color(0xFFE41E3F);

  // Typography on dark gradient
  static const onCallSurface       = Color(0xFFFFFFFF);
  static const onCallSurfaceMuted  = Color(0xCCFFFFFF); // 80%
}

class MessengerRadii {
  static const bubble       = 18.0;
  static const bubbleInner  = 4.0;   // run-side corner
  static const pill         = 22.0;  // search + input
  static const image        = 16.0;
}

class MessengerSpacing {
  static const tile         = 72.0;  // conversation tile height
  static const avatarLg     = 56.0;  // conversation list
  static const avatarMd     = 36.0;  // app bar
  static const avatarSm     = 28.0;  // bubble run
  static const avatarHero   = 168.0; // in-call
}
```

### Reusable widgets

- `MessengerAvatar` — circular avatar with optional online dot, initials
  fallback, deterministic gradient by user id.
- `StackedAvatars` — group avatar composition (2 stacked / grid).
- `BubbleShape` — `ShapeBorder` that produces the run-aware rounded corners
  (encapsulates the `_runRadius` logic).
- `MessengerPillField` — pill-shaped text field used by search and input bar.
- `CallActionButton` — round 64dp/72dp button with optional label and
  Messenger's idle/active translucency states.
- `TypingDots` — three-dot loop animation, 600ms.
- `OnlineDot` — 12dp green dot with white border.
- `MessengerGradientBackground` — the call-screen gradient as a reusable
  background widget.

### Iconography

Use `flutter_svg` against `assets/icons/` and add the Messenger-style icons
the app doesn't have yet: `phone_filled`, `phone_down_filled`,
`mic_off_filled`, `speaker_filled`, `paper_plane_filled`, `pencil_compose`,
`reaction_*`. If the design system doesn't already vendor an icon set, pull
them from `cupertino_icons` + `Icons` first and swap to custom SVGs later.

Keep messaging-domain widgets (e.g. `MessageBubble` itself, which renders an
entity) in the app's `presentation/widgets/` instead.

---

## Suggested rollout order

1. **Step 1** — deps + native config; verify `melos bootstrap` succeeds.
2. **Step 2** — domain entities, enums, repository interfaces, use cases.
3. **Step 3a–b** — models + REST endpoints (run codegen, manually test via the existing `RestClient`).
4. **Step 3c–e** — `ChatSocketService` + `ChatRealtimeRepository` + DI.
5. **Step 5** — `ChatRealtimeCubit` wired into `app.dart`. Confirm WS connects after login (log events).
6. **Step 6** — Conversations list (read-only first, mutate via WS events).
7. **Step 7** — Conversation screen (history + send + receive). Ship messaging here.
8. **Step 4** — `WebRtcService`. Smoke-test `getUserMedia` + permission flow.
9. **Step 8** — `CallCubit` + IncomingCall + InCall screens. Test 1:1 audio first, then 3-way mesh.
10. **Step 9** — auto_route entries; Step 11 — root wiring polish; Step 12 — DS extraction.

Each rollout step ends with `melos run analyze` + manual smoke test on tablet
and mobile.

---

## Things to validate against the backend before coding

The backend plan defines the wire shapes; if you change any field names there
(snake_case ↔ camelCase, enum values, payload nesting), update the **same field
name** in the matching model in `packages/data/lib/models/messaging/` and
re-run codegen — `fieldRename: FieldRename.snake` does the conversion
automatically as long as Dart names are camelCase.

For WebRTC, double-check that the SDP and ICE payloads are forwarded
**verbatim** by the backend. Anything the server reformats will break the
handshake silently.
