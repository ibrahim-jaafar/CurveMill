using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using Microsoft.Win32;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;
using SolidWorks.Interop.swpublished;

// Thin SolidWorks add-in: two ribbon buttons that launch CurveMill. Zero geometry
// logic — the app pulls the face over COM (see plan §7). The buttons fire blindly;
// CurveMill's own single-instance guard decides open-new vs foreground-existing.
namespace CurveMill
{
    [Guid("6B1E2C40-9A3D-4E7F-B21C-5A0F7E2D9C11"), ComVisible(true)]
    public class CurveMillAddin : SwAddin
    {
        private const string AppRegKey = @"SOFTWARE\CurveMill";  // installer (v4.0) writes ExePath/BaseArgs here
        private const int CmdGroupId = 0x4375724D;  // "CurM" - unique group id; small ids (1) collide with SW's own toolbars
        private const int OpenCmdId = 10;
        private const int SendCmdId = 11;
        private const string TabName = "CurveMill";
        private ISldWorks _sw;
        private int _cookie;
        private int _openCmdID, _sendCmdID;  // runtime command ids used to build the ribbon tab
        private SldWorks _events;            // idle hook: reload the command UI after SW's startup ribbon restore
        // Per-doc-type reload latch. SW clobbers our command->callback binding the FIRST time
        // each document-type context (part, then later a fresh assembly) is realized -- not just
        // at startup -- so we heal each type on first sight and stay armed for the others for the
        // whole session. ponytail: latches by doc TYPE. If a *second* document of an already-fixed
        // type ever greys, escalate to per-document re-arming (track active-doc identity on idle).
        private int _settleType;             // doc type currently in its settle window; 0 = none
        private DateTime _settleSince = System.DateTime.MinValue;
        private int _settleShots;            // reload-equivalents fired for _settleType so far
        private readonly HashSet<int> _fixedTypes = new HashSet<int>();  // types healed this session

        // Diagnostic log (%LOCALAPPDATA%\CurveMill\addin.log). Swallows all errors.
        private static void Log(string msg)
        {
            try
            {
                string dir = System.IO.Path.Combine(
                    System.Environment.GetFolderPath(System.Environment.SpecialFolder.LocalApplicationData),
                    "CurveMill");
                System.IO.Directory.CreateDirectory(dir);
                System.IO.File.AppendAllText(System.IO.Path.Combine(dir, "addin.log"),
                    System.DateTime.Now.ToString("HH:mm:ss.fff") + "  " + msg + System.Environment.NewLine);
            }
            catch { }
        }

        // int[] (boxed as object by GetGroupDataFromRegistry) -> "10,11" for the log.
        private static string FormatIds(object ids)
        {
            int[] a = ids as int[];
            if (a == null) return "(none)";
            return string.Join(",", a);
        }

        // --- ISwAddin ---
        public bool ConnectToSW(object ThisSW, int cookie)
        {
            _sw = (ISldWorks)ThisSW;
            _cookie = cookie;
            try
            {
                Log("ConnectToSW enter, cookie=" + cookie);
                _sw.SetAddinCallbackInfo2(0, this, cookie);
                CreateCommandUI();
                // The UI built here works during startup, then SW restores its cached ribbon as
                // the first part loads and greys our buttons with a foreign tooltip. Only a real
                // add-in reload fixes it: the log proved a tab-only rebuild is NOT enough, because
                // the working reload also re-runs SetAddinCallbackInfo2 (re-binding SW's
                // command->callback dispatch) and recreates the group ~2-3s after the part is up.
                // Replicate that on idle once a part/assembly is active. See OnIdleReload.
                _events = (SldWorks)_sw;
                _events.OnIdleNotify += OnIdleReload;
                Log("ConnectToSW ok (idle reload armed)");
                return true;
            }
            catch (Exception ex)
            {
                Log("ConnectToSW EXCEPTION: " + ex);
                return true;  // keep the add-in loaded even if UI setup threw
            }
        }

        // Create the command group, its two items, and the ribbon tab.
        // Heavily instrumented: this same method runs on a cold-start load AND on a
        // manual Add-In-Manager reload, so comparing two log entries tells us whether
        // the working (reload) runtime command ids differ from the broken (cold) ones.
        private void CreateCommandUI()
        {
            ICommandManager cmdMgr = _sw.GetCommandManager(_cookie);

            // What USER command ids did SW cache for our group last session? If they don't
            // match our current {OpenCmdId, SendCmdId}, canonical guidance says pass
            // IgnorePreviousVersion=true (we always do). Reveals leftover {0,1} from the
            // pre-bump builds, or a stale ribbon layout SW might be restoring.
            object regIds = null;
            bool haveReg = cmdMgr.GetGroupDataFromRegistry(CmdGroupId, out regIds);
            Log("registry: have=" + haveReg + " userIDs=" + FormatIds(regIds)
                + " (current known=" + OpenCmdId + "," + SendCmdId + ")");

            int err = 0;
            ICommandGroup grp = cmdMgr.CreateCommandGroup2(
                CmdGroupId, "CurveMill", "CurveMill for SOLIDWORKS", "", -1, true, ref err);
            Log("CreateCommandGroup2 err=" + err + " (1=Success) grp=" + (grp == null ? "NULL" : "ok"));
            if (grp == null) return;

            // PNG icons shipped next to the DLL (Resources\). IconList = per-size toolbar sprite
            // strips (cell 0 = Open, cell 1 = Send); MainIconList = the group icon. Set before items.
            grp.IconList = IconPaths("curvemill_toolbar");
            grp.MainIconList = IconPaths("curvemill_main");

            const int both = (int)swCommandItemType_e.swMenuItem | (int)swCommandItemType_e.swToolbarItem;
            int openIdx = grp.AddCommandItem2("Open CurveMill", -1, "Open CurveMill", "Open CurveMill",
                0, "OnOpen", "", OpenCmdId, both);
            int sendIdx = grp.AddCommandItem2("Send to CurveMill", -1,
                "Send the selected face or plane to CurveMill", "Send to CurveMill",
                1, "OnSend", "EnableSend", SendCmdId, both);
            grp.HasToolbar = true;
            grp.HasMenu = true;
            grp.Activate();

            _openCmdID = grp.get_CommandID(openIdx);
            _sendCmdID = grp.get_CommandID(sendIdx);
            // THE decisive line: runtime ids the ribbon buttons bind to. If a cold-start
            // load logs 41670/41671 but a manual reload logs different numbers, the greying
            // is an id collision with SW's own commands (stamps/punches). If they're equal,
            // it's SW-side callback binding that only a true reload refreshes.
            Log("built: runtime open=" + _openCmdID + " send=" + _sendCmdID
                + " toolbarId=" + grp.ToolbarId + " hasEnabledButton=" + grp.HasEnabledButton);

            BuildTabs(cmdMgr);
            Log("tabs built");
        }

        // (Re)create the ribbon tab for part & assembly docs from the stored runtime command
        // ids. Safe to call repeatedly -- it removes any existing CurveMill tab first. Split
        // out of CreateCommandUI so the idle handler can re-assert the tab without rebuilding
        // the (already-correct) command group.
        private void BuildTabs(ICommandManager cmdMgr)
        {
            int[] cmdIds = { _openCmdID, _sendCmdID };
            int[] textType = {
                (int)swCommandTabButtonTextDisplay_e.swCommandTabButton_TextBelow,
                (int)swCommandTabButtonTextDisplay_e.swCommandTabButton_TextBelow };
            foreach (int docType in new[] { (int)swDocumentTypes_e.swDocPART, (int)swDocumentTypes_e.swDocASSEMBLY })
            {
                CommandTab existing = cmdMgr.GetCommandTab(docType, TabName);
                if (existing != null) cmdMgr.RemoveCommandTab(existing);
                CommandTab tab = cmdMgr.AddCommandTab(docType, TabName);
                if (tab == null) { Log("AddCommandTab NULL docType=" + docType); continue; }
                tab.AddCommandTabBox().AddCommands(cmdIds, textType);
            }
        }

        // Fires on every SW idle. Heals the command->callback binding once per document-type
        // context. When a part/assembly becomes active whose type we haven't healed yet, wait for
        // its ribbon to settle then fire the in-process reload-equivalent -- twice, because the
        // broken and working states are API-identical (same ids, same HasEnabledButton), so we
        // can't read back whether the first shot took; the second brackets a slower settle.
        // We DON'T unhook after the first type: SW re-clobbers the binding the first time each
        // NEW type context appears (e.g. making an assembly from a part), so we stay armed and
        // heal that type when it shows up. See _fixedTypes / _settleType.
        private int OnIdleReload()
        {
            try
            {
                if (_events == null) return 0;
                IModelDoc2 doc = (IModelDoc2)_sw.IActiveDoc2;
                if (doc == null) return 0;  // no active doc yet
                int dt = doc.GetType();
                // Only part & assembly carry a CurveMill tab; drawings never do.
                if (dt != (int)swDocumentTypes_e.swDocPART && dt != (int)swDocumentTypes_e.swDocASSEMBLY)
                    return 0;
                if (_fixedTypes.Contains(dt)) return 0;  // this type's context already healed this session

                // (Re)start the settle window for whichever type just became active.
                if (_settleType != dt)
                {
                    _settleType = dt;
                    _settleSince = System.DateTime.Now;
                    _settleShots = 0;
                    return 0;
                }
                double elapsed = (System.DateTime.Now - _settleSince).TotalSeconds;
                // ponytail: 3s / 8s bracket SW's ribbon-restore settle window (the working manual
                // reload landed ~2.3s after the doc opened). Bump both if a slow machine still greys.
                if (_settleShots == 0 && elapsed >= 3.0) { ReloadEquivalent(); _settleShots = 1; return 0; }
                if (_settleShots >= 1 && elapsed >= 8.0)
                {
                    ReloadEquivalent();
                    _fixedTypes.Add(dt);  // this type is done; stay armed for the other type
                    _settleType = 0;
                }
            }
            catch (Exception ex) { Log("OnIdleReload EXCEPTION: " + ex); }
            return 0;
        }

        // The in-process equivalent of a Tools>Add-Ins reload: re-bind the command callbacks
        // (SetAddinCallbackInfo2) AND recreate the whole command group + tab. Both halves matter
        // -- the callback re-bind is what a plain tab rebuild was missing.
        private void ReloadEquivalent()
        {
            Log("reload-equivalent shot " + (_settleShots + 1) + " docType=" + _settleType);
            _sw.SetAddinCallbackInfo2(0, this, _cookie);
            RemoveCommandUI();
            CreateCommandUI();
            Log("reload-equivalent done");
        }

        // Remove the ribbon tab and command group (the teardown half of a reload).
        private void RemoveCommandUI()
        {
            ICommandManager cmdMgr = _sw.GetCommandManager(_cookie);
            foreach (int docType in new[] { (int)swDocumentTypes_e.swDocPART, (int)swDocumentTypes_e.swDocASSEMBLY })
            {
                CommandTab tab = cmdMgr.GetCommandTab(docType, TabName);
                if (tab != null) cmdMgr.RemoveCommandTab(tab);
            }
            cmdMgr.RemoveCommandGroup2(CmdGroupId, false);  // RuntimeOnly=false: drop the registry group data too
        }

        public bool DisconnectFromSW()
        {
            Log("DisconnectFromSW");
            if (_events != null) { _events.OnIdleNotify -= OnIdleReload; _events = null; }
            RemoveCommandUI();
            _sw = null;
            GC.Collect();
            GC.WaitForPendingFinalizers();
            return true;
        }

        private static string[] IconPaths(string prefix)
        {
            int[] sizes = { 20, 32, 40, 64, 96, 128 };
            string dir = System.IO.Path.Combine(
                System.IO.Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location),
                "Resources");
            string[] paths = new string[sizes.Length];
            for (int i = 0; i < sizes.Length; i++)
                paths[i] = System.IO.Path.Combine(dir, prefix + "_" + sizes[i] + ".png");
            return paths;
        }

        // --- button callbacks ---
        // Block bodies (not `=>`): the Framework's built-in Csc is C# 5 and rejects
        // expression-bodied members.
        public void OnOpen() { Launch(getSelection: false); }
        public void OnSend() { Launch(getSelection: true); }

        // "Send" enables only when exactly one face or plane is selected in a part/assembly.
        // Selection TYPE only — never reads geometry, must be fast, swallows COM errors.
        public int EnableSend()
        {
            try
            {
                var doc = (IModelDoc2)_sw.IActiveDoc2;
                if (doc == null || doc.GetType() == (int)swDocumentTypes_e.swDocDRAWING) return 0;
                var sel = (ISelectionMgr)doc.SelectionManager;
                if (sel.GetSelectedObjectCount2(-1) != 1) return 0;
                int t = sel.GetSelectedObjectType3(1, -1);
                return (t == (int)swSelectType_e.swSelFACES || t == (int)swSelectType_e.swSelDATUMPLANES) ? 1 : 0;
            }
            catch { return 0; }  // ponytail: any COM hiccup -> just grey it out
        }

        private void Launch(bool getSelection)
        {
            string exe = (string)Registry.GetValue(@"HKEY_LOCAL_MACHINE\" + AppRegKey, "ExePath", null);
            if (string.IsNullOrEmpty(exe))
            {
                _sw.SendMsgToUser2("CurveMill is not installed (registry key SOFTWARE\\CurveMill\\ExePath is missing).",
                    (int)swMessageBoxIcon_e.swMbWarning, (int)swMessageBoxBtn_e.swMbOk);
                return;
            }
            string args = (string)Registry.GetValue(@"HKEY_LOCAL_MACHINE\" + AppRegKey, "BaseArgs", "") ?? "";
            if (getSelection) args = (args + " --get-selection").Trim();
            // CreateNoWindow: kill the console window a console-subsystem exe (python.exe,
            // a console-built launcher) would pop up -- users were closing it by accident and
            // it cluttered the taskbar. Harmless when exe is already GUI (pythonw.exe/Qt).
            var psi = new ProcessStartInfo(exe, args) { UseShellExecute = false, CreateNoWindow = true };
            // SolidWorks poisons USERPROFILE to its own install dir for child processes, so
            // Python's expanduser("~") lands in Program Files (ezdxf cache write fails, etc.).
            // Restore the genuine profile path (known-folder lookup, not the poisoned env var).
            psi.EnvironmentVariables["USERPROFILE"] =
                System.Environment.GetFolderPath(System.Environment.SpecialFolder.UserProfile);
            try { Process.Start(psi); }
            catch (Exception ex)
            {
                _sw.SendMsgToUser2("Could not launch CurveMill: " + ex.Message,
                    (int)swMessageBoxIcon_e.swMbWarning, (int)swMessageBoxBtn_e.swMbOk);
            }
        }

        // --- COM (un)registration: regasm writes the SolidWorks AddIns keys ---
        [ComRegisterFunction]
        public static void RegisterFunction(Type t)
        {
            string guid = "{" + t.GUID.ToString().ToUpperInvariant() + "}";
            using (var k = Registry.LocalMachine.CreateSubKey(@"SOFTWARE\SolidWorks\Addins\" + guid))
            {
                k.SetValue(null, 0);  // 0 = loaded on demand; SW toggles this
                k.SetValue("Title", "CurveMill");
                k.SetValue("Description", "Launch CurveMill from SOLIDWORKS");
            }
            using (var k = Registry.CurrentUser.CreateSubKey(@"Software\SolidWorks\AddInsStartup\" + guid))
                k.SetValue(null, 1);  // enabled at startup for the current user
        }

        [ComUnregisterFunction]
        public static void UnregisterFunction(Type t)
        {
            string guid = "{" + t.GUID.ToString().ToUpperInvariant() + "}";
            Registry.LocalMachine.DeleteSubKey(@"SOFTWARE\SolidWorks\Addins\" + guid, false);
            Registry.CurrentUser.DeleteSubKey(@"Software\SolidWorks\AddInsStartup\" + guid, false);
        }
    }
}
