using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

// KIIS 테스트베드 원클릭 실행용: 에디터가 뜨면(또는 요청 파일이 생기면) 차량 씬을 열고 Play에 들어간다.
//   - 에디터를 "-kiisAutoPlay" 인자로 띄우면 컴파일·임포트가 끝난 뒤 한 번 자동 Play
//   - 이미 열린 에디터: 프로젝트의 Temp/kiis_play.request 파일이 생기면 Play (launcher/start_testbed.ps1이 만든다)
// 지금 씬에 'car'(TwinBootstrap이 트윈을 붙이는 오브젝트)가 없으면 Assets/Scenes/SampleScene(차량 모델 씬)을 연다.
// 그 씬이 없으면(공개 저장소) 지금 씬 그대로 Play — TwinBootstrap이 상자 차량을 만든다.
[InitializeOnLoad]
public static class KiisAutoPlay
{
    const string Scene = "Assets/Scenes/SampleScene.unity";
    const string SessionKey = "kiis.autoplay.done";
    static readonly string RequestFile = Path.GetFullPath(Path.Combine(Application.dataPath, "../Temp/kiis_play.request"));
    static bool pending;
    static double nextPoll;

    static KiisAutoPlay()
    {
        if (Array.IndexOf(Environment.GetCommandLineArgs(), "-kiisAutoPlay") >= 0 && !SessionState.GetBool(SessionKey, false))
        {
            SessionState.SetBool(SessionKey, true);   // Play 진입·종료 때 도메인이 다시 로드돼도 한 번만
            pending = true;
        }
        EditorApplication.update += Poll;
    }

    static void Poll()
    {
        if (EditorApplication.timeSinceStartup < nextPoll) return;
        nextPoll = EditorApplication.timeSinceStartup + 0.5;
        if (File.Exists(RequestFile))
        {
            try { File.Delete(RequestFile); } catch (Exception) { }
            pending = true;
        }
        if (!pending || EditorApplication.isPlayingOrWillChangePlaymode) { if (EditorApplication.isPlaying) pending = false; return; }
        if (EditorApplication.isCompiling || EditorApplication.isUpdating) return;
        pending = false;
        if (GameObject.Find("car") == null && File.Exists(Path.GetFullPath(Path.Combine(Application.dataPath, "..", Scene))))
        {
            if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;   // 사용자가 취소하면 Play 안 함
            EditorSceneManager.OpenScene(Scene, OpenSceneMode.Single);
        }
        Debug.Log("[KiisAutoPlay] Play 진입 (디지털 트윈 TCP 55002)");
        EditorApplication.EnterPlaymode();
    }
}
