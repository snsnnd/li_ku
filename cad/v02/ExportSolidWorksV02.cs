using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

// Converts our new V02 STEP parts only. No ExitApp, no closing user documents.
// Native output is a positioned B-rep assembly, NOT a native Motion Study.
internal static class ExportSolidWorksV02
{
    public sealed class PartRow
    {
        public string name { get; set; }
        public string material { get; set; }
        public double[] extents_mm { get; set; }
    }
    public sealed class InstanceRow
    {
        public string name { get; set; }
        public string part { get; set; }
        public double[] origin_mm { get; set; }
    }
    public sealed class Manifest
    {
        public string generator_sha256 { get; set; }
        public List<PartRow> parts { get; set; }
        public List<InstanceRow> instances { get; set; }
    }
    public sealed class SnapshotPart
    {
        public string step_data_sha256 { get; set; }
        public string native_file_sha256 { get; set; }
    }
    public sealed class Snapshot
    {
        public Dictionary<string, SnapshotPart> parts { get; set; }
    }
    public sealed class PriorPart { public string name { get; set; } }
    public sealed class PriorReport { public List<PriorPart> parts { get; set; } }
    private static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = 16000000 };

    private static string Hash(byte[] bytes)
    {
        using (SHA256 h = SHA256.Create()) return BitConverter.ToString(h.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
    }
    private static string StepHash(string path)
    {
        string s = File.ReadAllText(path).Replace("\r\n", "\n");
        return Hash(Encoding.UTF8.GetBytes(s.Substring(s.IndexOf("DATA;", StringComparison.Ordinal)+5)));
    }
    private static Body2 Cut(Body2 body, Body2 tool)
    {
        int error;
        Array result = body.Operations2((int)swBodyOperationType_e.SWBODYCUT, tool, out error) as Array;
        if (error != 0 || result == null || result.Length != 1) throw new InvalidOperationException("CSG cut failed: " + error);
        return (Body2)result.GetValue(0);
    }
    private static Body2 Box(Modeler m, double x, double y, double z, double w, double d, double h)
    {
        return (Body2)m.CreateBodyFromBox3(new double[] {x/1000,y/1000,z/1000,0,0,1,w/1000,d/1000,h/1000});
    }
    private static Body2 Cylinder(Modeler m, double x, double y, double z, double dx, double dy, double dz, double r, double h)
    {
        return (Body2)m.CreateBodyFromCyl(new double[] {x/1000,y/1000,z/1000,dx,dy,dz,r/1000,h/1000});
    }
    private static ModelDoc2 BuildTube(SldWorks app, string template)
    {
        // Same frozen tube geometry as asrs_v02.py; avoids the hanging STEP tube import.
        Modeler m = (Modeler)app.GetModeler();
        Body2 body = Cut(Box(m,0,-114.5,0,25,227,25), Box(m,0,-114.5,2,21,229,21));
        foreach (double y in new double[] {-121,-31,-110,-50}) body = Cut(body, Cylinder(m,0,y,-1,0,0,1,2.25,27));
        body = Cut(body, Cylinder(m,-14,-208,12.5,1,0,0,2.75,28));
        ModelDoc2 doc = (ModelDoc2)app.NewDocument(template,0,0,0);
        if (((PartDoc)doc).CreateFeatureFromBody3(body,false,0) == null) throw new InvalidOperationException("Native tube feature failed");
        return doc;
    }

    private static void Save(ModelDoc2 doc, string path)
    {
        if (File.Exists(path)) throw new IOException("Refusing overwrite: " + path);
        int errors = 0, warnings = 0;
        bool ok = doc.Extension.SaveAs(path, 0, 1, null, ref errors, ref warnings);
        if (!ok || errors != 0 || !File.Exists(path) || new FileInfo(path).Length == 0)
            throw new IOException("Save failed: " + path + ", errors=" + errors + ", warnings=" + warnings);
    }

    [STAThread]
    private static int Main(string[] args)
    {
        string source = args.Length > 0 ? Path.GetFullPath(args[0]) : @"D:\立库\model\V02";
        string output = args.Length > 1 ? Path.GetFullPath(args[1]) : Path.Combine(source, "native");
        bool resume = args.Length > 2 && args[2] == "--resume-verified";
        if (Directory.Exists(output) && !resume) { Console.Error.WriteLine("Use a NEW native output directory: " + output); return 2; }
        Manifest manifest = Json.Deserialize<Manifest>(File.ReadAllText(Path.Combine(source, "manifest.json")));
        string template = @"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2025\templates\gb_assembly.asmdot";
        if (!File.Exists(template)) throw new FileNotFoundException(template);
        SldWorks app = (SldWorks)Marshal.GetActiveObject("SldWorks.Application");
        app.Visible = true;
        HashSet<string> reusable = new HashSet<string>();
        if (resume)
        {
            Snapshot snapshot = Json.Deserialize<Snapshot>(File.ReadAllText(Path.Combine(source,"native_source_snapshot.json")));
            PriorReport prior = Json.Deserialize<PriorReport>(File.ReadAllText(Path.Combine(output,"solidworks_validation.json")));
            foreach (PriorPart p in prior.parts)
            {
                SnapshotPart recorded;
                string native = Path.Combine(output,"parts",p.name+".SLDPRT");
                if (!snapshot.parts.TryGetValue(p.name,out recorded) ||
                    recorded.step_data_sha256 != StepHash(Path.Combine(source,"parts",p.name+".step")) ||
                    recorded.native_file_sha256 != Hash(File.ReadAllBytes(native)))
                    throw new InvalidOperationException("Cannot safely reuse changed artifact: " + p.name);
                reusable.Add(p.name);
            }
            string backup = Path.Combine(output,"solidworks_validation.before_resume.json");
            if (File.Exists(backup)) throw new IOException("Resume backup already exists");
            File.Copy(Path.Combine(output,"solidworks_validation.json"),backup);
            Array docs = app.GetDocuments() as Array;
            List<string> close = new List<string>();
            if (docs != null) foreach (object o in docs)
            {
                ModelDoc2 d = (ModelDoc2)o;
                if (d.GetPathName().StartsWith(output+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))
                {
                    if (d.GetSaveFlag()) throw new InvalidOperationException("Refusing to close an unsaved document: " + d.GetPathName());
                    close.Add(d.GetTitle());
                }
            }
            foreach (string title in close) app.CloseDoc(title);
        }
        Directory.CreateDirectory(Path.Combine(output, "parts"));
        List<object> parts = new List<object>();
        List<object> components = new List<object>();
        Dictionary<string, object> report = new Dictionary<string, object>();
        report["generator_sha256"] = manifest.generator_sha256;
        report["solidworks_revision"] = app.RevisionNumber();
        report["native_parametric_feature_history"] = false;
        report["native_motion_mates_verified"] = false;
        report["hardware_accepted"] = false;
        report["parts"] = parts;
        report["components"] = components;
        report["status"] = "in_progress";
        int partPref = (int)swUserPreferenceStringValue_e.swDefaultTemplatePart;
        int asmPref = (int)swUserPreferenceStringValue_e.swDefaultTemplateAssembly;
        int templateToggle = (int)swUserPreferenceToggle_e.swAlwaysUseDefaultTemplates;
        int importToggle = (int)swUserPreferenceToggle_e.swMultiCAD_Enable3DInterconnect;
        string oldPart = app.GetUserPreferenceStringValue(partPref);
        string oldAssembly = app.GetUserPreferenceStringValue(asmPref);
        bool oldTemplateToggle = app.GetUserPreferenceToggle(templateToggle);
        bool oldImportToggle = app.GetUserPreferenceToggle(importToggle);
        report["original_preferences"] = new { part_template = oldPart, assembly_template = oldAssembly,
            always_use_defaults = oldTemplateToggle, use_3d_interconnect = oldImportToggle };
        try
        {
            string partTemplate = @"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2025\templates\gb_part.prtdot";
            if (!app.SetUserPreferenceStringValue(partPref, partTemplate) ||
                !app.SetUserPreferenceStringValue(asmPref, template))
                throw new InvalidOperationException("Cannot set temporary import/template preferences");
            app.SetUserPreferenceToggle(templateToggle, true);
            app.SetUserPreferenceToggle(importToggle, false);
            if (!app.GetUserPreferenceToggle(templateToggle) || app.GetUserPreferenceToggle(importToggle))
                throw new InvalidOperationException("Temporary import preference readback differs");
            int n = 0;
            foreach (PartRow row in manifest.parts)
            {
                string step = Path.Combine(source, "parts", row.name + ".step");
                int errors = 0;
                int warnings = 0;
                string native = Path.Combine(output, "parts", row.name + ".SLDPRT");
                bool reused = reusable.Contains(row.name);
                ModelDoc2 doc;
                if (reused) doc = (ModelDoc2)app.OpenDoc6(native,1,1,"",ref errors,ref warnings);
                else if (row.name == "Tray_Al_Tube_25x25x2_L227") doc = BuildTube(app,partTemplate);
                else
                {
                    ImportStepData data = (ImportStepData)app.GetImportFileData(step);
                    if (data != null) data.MapConfigurationData = true;
                    doc = (ModelDoc2)app.LoadFile4(step, "r", data, ref errors);
                }
                if (doc == null || errors != 0) throw new InvalidOperationException("Import failed " + row.name + ": " + errors);
                PartDoc part = doc as PartDoc;
                if (part == null) throw new InvalidOperationException("Not a part: " + row.name);
                Array bodies = part.GetBodies2(0, false) as Array;
                if (bodies == null || bodies.Length != 1) throw new InvalidOperationException("Not one solid: " + row.name);
                double[] bb = (double[])((Body2)bodies.GetValue(0)).GetBodyBox();
                double maxErrorMm = 0;
                for (int k = 0; k < 3; k++) maxErrorMm = Math.Max(maxErrorMm, Math.Abs((bb[k+3]-bb[k])*1000-row.extents_mm[k]));
                if (maxErrorMm > 0.2) throw new InvalidOperationException("Native bounding box differs: " + row.name + " / " + maxErrorMm);
                double[] appearance = { .64, .69, .73, .3, .7, .2, .3, 0, 0 };
                if (row.material == "PETG") { appearance[0] = .15; appearance[1] = .61; appearance[2] = .78; }
                if (row.material == "steel" || row.material == "purchased") { appearance[0] = .28; appearance[1] = .33; appearance[2] = .38; }
                if (row.material == "rubber") { appearance[0] = .12; appearance[1] = .14; appearance[2] = .16; }
                if (row.material == "safety") { appearance[0] = .90; appearance[1] = .28; appearance[2] = .15; }
                if (row.material == "guard") { appearance[0] = .57; appearance[1] = .79; appearance[2] = .85; appearance[7] = .85; }
                if (!reused)
                {
                    doc.MaterialPropertyValues = appearance; // APPEARANCE, not a physical engineering material.
                    doc.ForceRebuild3(false);
                    Save(doc, native);
                }
                parts.Add(new { name = row.name, file = native, body_count = bodies.Length, bounding_box_error_mm = maxErrorMm,
                    reused_with_fingerprint = reused, native_file_sha256 = Hash(File.ReadAllBytes(native)) });
                Console.WriteLine("NATIVE_PART " + (++n) + "/" + manifest.parts.Count + " " + row.name);
                if (doc.GetPathName().StartsWith(output+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))
                    app.CloseDoc(doc.GetTitle());
            }
            ModelDoc2 model = (ModelDoc2)app.NewDocument(template, 0, 0, 0);
            if (model == null) throw new InvalidOperationException("Cannot create assembly");
            AssemblyDoc assembly = (AssemblyDoc)model;
            MathUtility maths = (MathUtility)app.GetMathUtility();
            List<Component2> guards = new List<Component2>();
            n = 0;
            foreach (InstanceRow row in manifest.instances)
            {
                string partPath = Path.Combine(output,"parts",row.part+".SLDPRT");
                int openErrors=0,openWarnings=0,activateErrors=0;
                ModelDoc2 opened = (ModelDoc2)app.OpenDoc6(partPath,1,1,"",ref openErrors,ref openWarnings);
                if (opened == null || openErrors != 0) throw new InvalidOperationException("Cannot load component part: "+row.part);
                app.ActivateDoc3(model.GetTitle(),false,0,ref activateErrors);
                Component2 c = (Component2)assembly.AddComponent5(partPath, 0, "", false, "", 0, 0, 0);
                if (c == null) throw new InvalidOperationException("Insert failed: " + row.name);
                c.Name2 = row.name;
                double[] t = { 1,0,0,0,1,0,0,0,1, row.origin_mm[0]/1000, row.origin_mm[1]/1000, row.origin_mm[2]/1000, 1,0,0,0 };
                c.Transform2 = (MathTransform)maths.CreateTransform(t);
                double[] actual = (double[])c.Transform2.ArrayData;
                double err = 0;
                for (int k = 0; k < 13; k++) err = Math.Max(err, Math.Abs(actual[k]-t[k]));
                if (err > 1e-8) throw new InvalidOperationException("Transform readback differs: " + row.name);
                if (!c.Select4(false, null, false)) throw new InvalidOperationException("Select failed: " + row.name);
                assembly.FixComponent();
                model.ClearSelection2(true);
                if (row.part.StartsWith("Guard_")) guards.Add(c);
                components.Add(new { name = row.name, position_error_m = err });
                app.CloseDoc(opened.GetTitle());
                if (++n % 25 == 0) Console.WriteLine("NATIVE_COMPONENT " + n + "/" + manifest.instances.Count);
            }
            int count = ((Array)assembly.GetComponents(false)).Length;
            if (count != manifest.instances.Count) throw new InvalidOperationException("Component count differs: " + count);
            model.ForceRebuild3(false);
            model.ShowNamedView2("*Isometric", 7);
            model.ViewZoomtofit2();
            Save(model, Path.Combine(output, "ASRS_Modular_V02_enclosed.png"));
            foreach (Component2 guard in guards) guard.Visible = 0;
            model.ViewZoomtofit2();
            model.GraphicsRedraw2();
            Save(model, Path.Combine(output, "ASRS_Modular_V02_inspection.png"));
            foreach (Component2 guard in guards) guard.Visible = 1;
            string assemblyPath = Path.Combine(output, "ASRS_Modular_V02.SLDASM");
            Save(model, assemblyPath);
            report["assembly"] = assemblyPath;
            report["component_count"] = count;
            report["status"] = "native_positioned_assembly_saved";
            Console.WriteLine("NATIVE_ASSEMBLY_OK " + assemblyPath);
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
            try
            {
                app.SetUserPreferenceStringValue(partPref, oldPart);
                app.SetUserPreferenceStringValue(asmPref, oldAssembly);
                app.SetUserPreferenceToggle(templateToggle, oldTemplateToggle);
                app.SetUserPreferenceToggle(importToggle, oldImportToggle);
                report["temporary_preferences_restored"] =
                    app.GetUserPreferenceStringValue(partPref) == oldPart &&
                    app.GetUserPreferenceStringValue(asmPref) == oldAssembly &&
                    app.GetUserPreferenceToggle(templateToggle) == oldTemplateToggle &&
                    app.GetUserPreferenceToggle(importToggle) == oldImportToggle;
            }
            catch (Exception restoreError)
            {
                report["temporary_preferences_restored"] = false;
                report["preference_restore_error"] = restoreError.Message;
            }
            File.WriteAllText(Path.Combine(output, "solidworks_validation.json"), Json.Serialize(report));
        }
    }
}
