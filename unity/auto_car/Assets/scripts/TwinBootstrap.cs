using UnityEngine;

// Play를 누르면 씬의 car 오브젝트에 TwinFirmware를 자동으로 붙인다(씬 파일을 고치지 않기 위해).
// car가 없으면(공개 저장소처럼 차량 모델이 없는 경우, 또는 빈 씬) TwinPlaceholder로 상자 차량을 만들어 붙인다.
// MATLAB 상태 수신(CarStateReceiver) 모드로 돌리고 싶으면 enabled를 false로 바꾸거나 이 파일을 지운다.
public static class TwinBootstrap
{
    public static bool enabled = true;
    public const string CarName = "car";

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void Attach()
    {
        if (!enabled) return;
        var car = GameObject.Find(CarName);
        if (car == null) car = TwinPlaceholder.Build(CarName);
        if (car.GetComponent<TwinFirmware>() == null) car.AddComponent<TwinFirmware>();
    }
}
