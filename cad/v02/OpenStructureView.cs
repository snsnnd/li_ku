using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;
using SolidWorks.Interop.sldworks;

// Open an independent viewing copy. No closing documents, preference edits or source saves.
internal static class OpenStructureView
{
    [STAThread]
    private static int Main(string[] args)
    {
        string source = args[0], directory = args[1];
        Directory.CreateDirectory(directory);
        var report = new Dictionary<string, object>();
        try
        {
            SldWorks app;
            try { app = (SldWorks)Marshal.GetActiveObject("SldWorks.Application"); }
            catch (COMException) { app = (SldWorks)Activator.CreateInstance(Type.GetTypeFromProgID("SldWorks.Application")); }
            app.Visible = true;
            bool activeView = args.Length > 2 && args[2] == "--active-z-up";
            Console.WriteLine("OPEN_STRUCTURE_VIEW " + source);
            int errors = 0;
            ModelDoc2 doc;
            if (activeView)
            {
                doc = (ModelDoc2)app.ActiveDoc;
                if (doc == null || !doc.GetTitle().StartsWith("ASRS_Modular_V02_INTERIOR_VIEW", StringComparison.Ordinal))
                    throw new InvalidOperationException("Refusing to adjust an unrelated active document");
            }
            else
            {
                ImportStepData data = (ImportStepData)app.GetImportFileData(source);
                if (data != null) data.MapConfigurationData = false;
                doc = (ModelDoc2)app.LoadFile4(source, "r", data, ref errors);
            }
            report["source"] = source;
            report["import_errors"] = errors;
            if (doc == null || errors != 0) throw new InvalidOperationException("View import failed: " + errors);
            report["title"] = doc.GetTitle();
            report["document_type"] = doc.GetType();
            PartDoc part = doc as PartDoc;
            if (part != null)
            {
                Array bodies = part.GetBodies2(0, false) as Array;
                report["solid_count"] = bodies == null ? 0 : bodies.Length;
            }
            ((ModelView)doc.ActiveView).EnableGraphicsUpdate = true;
            doc.ClearSelection2(true);
            doc.ShowNamedView2("*Isometric", 7);
            // Explicit Z-up camera basis: right=(1,1,0), up=(-1,1,2), toward eye=(1,-1,1).
            double r = 1/Math.Sqrt(2), u = 1/Math.Sqrt(6), n = 1/Math.Sqrt(3);
            double[] orientation = { r,-u,n, r,u,-n, 0,2*u,n, 0,0,0, 1,0,0,0 };
            MathUtility maths = (MathUtility)app.GetMathUtility();
            ((ModelView)doc.ActiveView).Orientation3 = (MathTransform)maths.CreateTransform(orientation);
            ((ModelView)doc.ActiveView).DisplayMode = 5; // swViewDisplayMode_ShadedWithEdges
            report["z_up_view_applied"] = true;
            doc.ViewZoomtofit2();
            doc.GraphicsRedraw2();
            report["bitmap_saved"] = doc.SaveBMP(Path.Combine(directory, "solidworks_view.bmp"), 1600, 1000);
            report["preferences_changed"] = false;
            report["source_saved"] = false;
            report["status"] = "opened";
            Console.WriteLine("STRUCTURE_VIEW_OPENED " + doc.GetTitle());
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
            File.WriteAllText(Path.Combine(directory, "solidworks_view_status.json"),
                new JavaScriptSerializer().Serialize(report));
        }
    }
}
