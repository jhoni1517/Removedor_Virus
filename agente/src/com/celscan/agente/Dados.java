package com.celscan.agente;

import android.app.usage.UsageStats;
import android.app.usage.UsageStatsManager;
import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.drawable.Drawable;
import android.net.Uri;
import android.os.Binder;
import android.os.Process;
import android.util.Base64;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

/**
 * Responde, só para o shell do adb, a três consultas (via "content query"):
 *   content://com.celscan.agente.dados/versao
 *   content://com.celscan.agente.dados/apps?icones=1   nome e ícone reais de todos os apps
 *   content://com.celscan.agente.dados/uso?dias=30     último uso e tempo em primeiro plano
 * Textos e ícones vão em Base64 (URL-safe) para a saída do "content query" ser fácil de ler sem ambiguidade.
 */
public class Dados extends ContentProvider {
    static final String VERSAO = "1";
    static final int LADO_ICONE = 72;

    @Override
    public boolean onCreate() {
        return true;
    }

    /** Só root, system e shell (o adb). Qualquer outro app recebe nada. */
    private static boolean confiavel() {
        int uid = Binder.getCallingUid();
        return uid == 0 || uid == Process.SYSTEM_UID || uid == 2000;
    }

    @Override
    public Cursor query(Uri uri, String[] projecao, String selecao, String[] args, String ordem) {
        if (!confiavel()) {
            return null;
        }
        String alvo = uri.getLastPathSegment();
        if ("versao".equals(alvo)) {
            MatrixCursor c = new MatrixCursor(new String[]{"versao"});
            c.addRow(new Object[]{VERSAO});
            return c;
        }
        if ("apps".equals(alvo)) {
            return apps(!"0".equals(uri.getQueryParameter("icones")));
        }
        if ("uso".equals(alvo)) {
            int dias = 30;
            try {
                dias = Integer.parseInt(uri.getQueryParameter("dias"));
            } catch (Exception ignorado) {
                // usa o padrão
            }
            return uso(Math.max(1, Math.min(dias, 365)));
        }
        return null;
    }

    private Cursor apps(boolean icones) {
        PackageManager pm = getContext().getPackageManager();
        MatrixCursor c = new MatrixCursor(new String[]{"pacote", "nome", "icone", "sistema", "instalado", "atualizado"});
        List<ApplicationInfo> lista = pm.getInstalledApplications(0);
        for (ApplicationInfo ai : lista) {
            String nome = ai.packageName;
            String icone = "";
            long instalado = 0, atualizado = 0;
            try {
                nome = String.valueOf(pm.getApplicationLabel(ai));
                if (icones) {
                    icone = png(pm.getApplicationIcon(ai));
                }
                PackageInfo pi = pm.getPackageInfo(ai.packageName, 0);
                instalado = pi.firstInstallTime;
                atualizado = pi.lastUpdateTime;
            } catch (Throwable ignorado) {
                // app removido no meio da leitura ou ícone inválido: segue com o que tem
            }
            int sistema = (ai.flags & (ApplicationInfo.FLAG_SYSTEM | ApplicationInfo.FLAG_UPDATED_SYSTEM_APP)) != 0 ? 1 : 0;
            c.addRow(new Object[]{ai.packageName, b64(nome), icone, sistema, instalado, atualizado});
        }
        return c;
    }

    private Cursor uso(int dias) {
        MatrixCursor c = new MatrixCursor(new String[]{"pacote", "ultimo_uso", "frente_ms"});
        UsageStatsManager usm = (UsageStatsManager) getContext().getSystemService(Context.USAGE_STATS_SERVICE);
        if (usm == null) {
            return c;
        }
        long fim = System.currentTimeMillis();
        long inicio = fim - dias * 86400000L;
        Map<String, UsageStats> mapa = usm.queryAndAggregateUsageStats(inicio, fim);
        for (Map.Entry<String, UsageStats> e : mapa.entrySet()) {
            UsageStats u = e.getValue();
            c.addRow(new Object[]{e.getKey(), u.getLastTimeUsed(), u.getTotalTimeInForeground()});
        }
        return c;
    }

    private static String b64(String s) {
        return Base64.encodeToString(s.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP | Base64.URL_SAFE);
    }

    private static String png(Drawable d) {
        Bitmap b = Bitmap.createBitmap(LADO_ICONE, LADO_ICONE, Bitmap.Config.ARGB_8888);
        Canvas tela = new Canvas(b);
        d.setBounds(0, 0, LADO_ICONE, LADO_ICONE);
        d.draw(tela);
        ByteArrayOutputStream saida = new ByteArrayOutputStream();
        b.compress(Bitmap.CompressFormat.PNG, 100, saida);
        b.recycle();
        return Base64.encodeToString(saida.toByteArray(), Base64.NO_WRAP | Base64.URL_SAFE);
    }

    @Override
    public String getType(Uri uri) {
        return null;
    }

    @Override
    public Uri insert(Uri uri, ContentValues valores) {
        return null;
    }

    @Override
    public int delete(Uri uri, String selecao, String[] args) {
        return 0;
    }

    @Override
    public int update(Uri uri, ContentValues valores, String selecao, String[] args) {
        return 0;
    }
}
