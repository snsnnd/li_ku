using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;
using SolidWorks.Interop.sldworks;

// Inspect the active document without saving, closing, or changing import options.
internal static class InspectActiveSolidWorks
{
    [StructLayout(LayoutKind.Sequential)]
    private struct Rect { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")]
    private static extern bool GetWindowRect(IntPtr window, out Rect rect);
    [DllImport("user32.dll")]
    private static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr window);
    [DllImport("user32.dll")]
    private static extern bool RedrawWindow(IntPtr window, IntPtr rect, IntPtr region, uint flags);

    private static object Bodies(PartDoc part)
    {
        var rows = new List<object>();
        Array bodies = part.GetBodies2(0, false) as Array;
        if (bodies != null) foreach (Body2 body in bodies)
            rows.Add(new { box_m = body.GetBodyBox() });
        return rows;
    }

    [STAThread]
    private static int Main(string[] args)
    {
        string directory = args[0];
        Directory.CreateDirectory(directory);
        var report = new Dictionary<string, object>();
        try
        {
            SldWorks app = (SldWorks)Marshal.GetActiveObject("SldWorks.Application");
            ModelDoc2 doc = (ModelDoc2)app.ActiveDoc;
            if (doc == null) throw new InvalidOperationException("No active SolidWorks document");
            report["title"] = doc.GetTitle();
            report["path"] = doc.GetPathName();
            report["document_type"] = doc.GetType();
            report["configuration"] = doc.ConfigurationManager.ActiveConfiguration.Name;
            ModelView view = (ModelView)doc.ActiveView;
            report["view_scale_before"] = view.Scale2;
            report["graphics_update_enabled_before"] = view.EnableGraphicsUpdate;
            report["view_orientation_before"] = ((MathTransform)view.Orientation3).ArrayData;
            report["view_translation_before"] = ((MathVector)view.Translation3).ArrayData;
            if (doc is AssemblyDoc)
            {
                var rows = new List<object>();
                Array components = ((AssemblyDoc)doc).GetComponents(false) as Array;
                if (components != null) foreach (Component2 c in components)
                {
                    var row = new Dictionary<string, object>();
                    row["name"] = c.Name2;
                    row["path"] = c.GetPathName();
                    row["visibility"] = c.Visible;
                    row["hidden"] = c.IsHidden(false);
                    row["suppression"] = c.GetSuppression();
                    ModelDoc2 model = (ModelDoc2)c.GetModelDoc2();
                    row["model_loaded"] = model != null;
                    if (model is PartDoc) row["bodies"] = Bodies((PartDoc)model);
                    if (c.Transform2 != null) row["transform"] = c.Transform2.ArrayData;
                    rows.Add(row);
                }
                report["components"] = rows;
            }
            else if (doc is PartDoc) report["bodies"] = Bodies((PartDoc)doc);
            if (args.Length > 1 && args[1] == "--fit")
            {
                view.EnableGraphicsUpdate = true;
                doc.ClearSelection2(true);
                doc.ShowNamedView2("*Isometric", 7);
                doc.ViewZoomtofit2();
                doc.GraphicsRedraw2();
                report["view_fitted"] = true;
                report["view_scale_after"] = view.Scale2;
                report["view_orientation_after"] = ((MathTransform)view.Orientation3).ArrayData;
                report["view_translation_after"] = ((MathVector)view.Translation3).ArrayData;
            }
            SetProcessDPIAware();
            foreach (Process p in Process.GetProcessesByName("SLDWORKS"))
            {
                Rect rect;
                if (p.MainWindowHandle == IntPtr.Zero || !GetWindowRect(p.MainWindowHandle, out rect)) continue;
                if (args.Length > 1 && args[1] == "--fit")
                {
                    SetForegroundWindow(p.MainWindowHandle);
                    RedrawWindow(p.MainWindowHandle, IntPtr.Zero, IntPtr.Zero, 0x185);
                }
                int w = rect.Right-rect.Left, h = rect.Bottom-rect.Top;
                if (w <= 0 || h <= 0) continue;
                using (Bitmap bitmap = new Bitmap(w, h))
                using (Graphics g = Graphics.FromImage(bitmap))
                {
                    g.CopyFromScreen(rect.Left, rect.Top, 0, 0, new Size(w, h));
                    bitmap.Save(Path.Combine(directory, "active_solidworks.png"));
                }
            }
            report["status"] = "inspected";
            return 0;
        }
        catch (Exception ex)
        {
            report["status"] = "failed";
            report["error"] = ex.ToString();
            Console.Error.WriteLine(ex);
            return 1;
        }
        finally
        {
            File.WriteAllText(Path.Combine(directory, "active_document.json"),
                new JavaScriptSerializer { MaxJsonLength = 16000000 }.Serialize(report));
            Console.WriteLine("DIAGNOSTIC " + Path.Combine(directory, "active_document.json"));
        }
    }
}
