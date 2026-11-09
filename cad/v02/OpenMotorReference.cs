using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

// Opens the supplied motor reference without saving over it or changing preferences.
internal static class OpenMotorReference
{
    [STAThread]
    private static int Main(string[] args)
    {
        string path = args[0];
        string reportPath = args[1];
        var report = new Dictionary<string, object>();
        try
        {
            SldWorks app = (SldWorks)Marshal.GetActiveObject("SldWorks.Application");
            app.Visible = true;
            report["solidworks_revision"] = app.RevisionNumber();
            report["source"] = path;
            report["preferences_changed"] = false;
            report["default_part_template"] = app.GetUserPreferenceStringValue((int)swUserPreferenceStringValue_e.swDefaultTemplatePart);
            report["default_assembly_template"] = app.GetUserPreferenceStringValue((int)swUserPreferenceStringValue_e.swDefaultTemplateAssembly);
            report["always_use_default_templates"] = app.GetUserPreferenceToggle((int)swUserPreferenceToggle_e.swAlwaysUseDefaultTemplates);
            report["enable_3d_interconnect"] = app.GetUserPreferenceToggle((int)swUserPreferenceToggle_e.swMultiCAD_Enable3DInterconnect);
            ModelDoc2 doc = (ModelDoc2)app.GetOpenDocumentByName(path);
            int errors = 0;
            if (doc == null)
            {
                Console.WriteLine("OPEN_MOTOR_REFERENCE " + path);
                ImportStepData data = (ImportStepData)app.GetImportFileData(path);
                if (data != null) data.MapConfigurationData = true;
                doc = (ModelDoc2)app.LoadFile4(path, "r", data, ref errors);
            }
            report["import_errors"] = errors;
            if (doc == null || errors != 0) throw new InvalidOperationException("Motor reference import failed: " + errors);
            doc.ShowNamedView2("*Isometric", 7);
            doc.ViewZoomtofit2();
            doc.GraphicsRedraw2();
            report["title"] = doc.GetTitle();
            report["document_type"] = doc.GetType();
            PartDoc part = doc as PartDoc;
            if (part != null)
            {
                Array bodies = part.GetBodies2(0, false) as Array;
                report["solid_body_count"] = bodies == null ? 0 : bodies.Length;
            }
            report["status"] = "opened_without_saving_source";
            Console.WriteLine("MOTOR_REFERENCE_OPENED " + doc.GetTitle());
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
            Directory.CreateDirectory(Path.GetDirectoryName(reportPath));
            File.WriteAllText(reportPath, new JavaScriptSerializer().Serialize(report));
        }
    }
}
