// MultiWallpaper —— 每显示器独立壁纸（IDesktopWallpaper COM）
// 用法:
//   multiwallpaper.exe             → 列出所有显示器 device path（每行一个）
//   multiwallpaper.exe "dev=path" ...  → 为指定显示器设置壁纸
using System;
using System.Runtime.InteropServices;
using System.Text;

class MultiWallpaper
{
    [StructLayout(LayoutKind.Sequential)]
    struct RECT { public int Left, Top, Right, Bottom; }

    [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown),
     Guid("B92B56A9-8B55-4E14-9A89-0199BBB6F93B")]
    interface IDesktopWallpaper
    {
        [PreserveSig] int GetMonitorDevicePathAt(uint index, [MarshalAs(UnmanagedType.LPWStr)] StringBuilder id);
        [PreserveSig] int GetMonitorDevicePathCount(out uint count);
        [PreserveSig] int GetMonitorRECT([MarshalAs(UnmanagedType.LPWStr)] string id, out RECT rect);
        [PreserveSig] int SetWallpaper([MarshalAs(UnmanagedType.LPWStr)] string id, [MarshalAs(UnmanagedType.LPWStr)] string path);
        [PreserveSig] int GetWallpaper([MarshalAs(UnmanagedType.LPWStr)] string id, [MarshalAs(UnmanagedType.LPWStr)] StringBuilder path);
        [PreserveSig] int GetPosition();
        [PreserveSig] int SetPosition(int position);
        [PreserveSig] int GetBackgroundColor(out uint color);
        [PreserveSig] int SetBackgroundColor(uint color);
        [PreserveSig] int GetSlideshow(out object slideshow, out int options);
        [PreserveSig] int SetSlideshow(object slideshow);
        [PreserveSig] int SetSlideshowOptions(int options, uint time, uint type);
        [PreserveSig] int GetSlideshowOptions(out int options, out uint time, out uint type);
        [PreserveSig] int AdvanceSlideshow([MarshalAs(UnmanagedType.LPWStr)] string id, int direction);
        [PreserveSig] int GetStatus();
        [PreserveSig] int Enable();
    }

    [ComImport, Guid("C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD")]
    class DesktopWallpaper { }

    static int Main(string[] args)
    {
        IDesktopWallpaper dw;
        try
        {
            dw = (IDesktopWallpaper)new DesktopWallpaper();
        }
        catch (Exception e)
        {
            Console.Error.WriteLine("CreateInstance failed: " + e.Message);
            return 1;
        }
        uint n;
        int hr = dw.GetMonitorDevicePathCount(out n);
        if (hr != 0)
        {
            Console.Error.WriteLine("GetMonitorDevicePathCount failed hr=0x" + hr.ToString("X8"));
            return 1;
        }

        if (args.Length == 0)
        {
            // 列表模式
            for (uint i = 0; i < n; i++)
            {
                StringBuilder sb = new StringBuilder(260);
                if (dw.GetMonitorDevicePathAt(i, sb) == 0)
                    Console.WriteLine(sb.ToString());
            }
            return 0;
        }

        // 设置模式: "device=path"
        int ok = 0, fail = 0;
        foreach (string a in args)
        {
            int eq = a.IndexOf('=');
            if (eq <= 0) continue;
            string dev = a.Substring(0, eq);
            string path = a.Substring(eq + 1);
            if (dw.SetWallpaper(dev, path) == 0) ok++; else fail++;
        }
        if (fail > 0) { Console.Error.WriteLine(fail + " monitor(s) failed"); return 1; }
        Console.WriteLine(ok + " monitor(s) set");
        return 0;
    }
}
