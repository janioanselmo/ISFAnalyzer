from __future__ import annotations

from pathlib import Path
import hashlib

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from streamlit_image_coordinates import streamlit_image_coordinates
except ImportError:  # optional component; app still runs without image-click selection
    streamlit_image_coordinates = None

from ensaisf.application.metrics_tables import *
from ensaisf.application.power_analysis import *
from ensaisf.channels import (
    matching_current_for_voltage,
    names_for_role,
    sort_items_by_pulse,
)
from ensaisf.domain.channel_metrics import *
from ensaisf.domain.envelope_analysis import *
from ensaisf.infrastructure.csv_exporter import *
from ensaisf.presentation.formatting import *
from ensaisf.presentation.plots import *
from ensaisf.presentation.theme import (
    ENVELOPE_IMAGE_MAX_POINTS,
    POWER_PLOT_MAX_POINTS,
    SERIES_COLORS_HEX,
)
from ensaisf.analysis import (
    compare_ringdown_metrics,
    decimate_for_plot,
    resonance_shift_score,
    ringdown_metrics,
    waveform_similarity_metrics,
)

def render_envelope_page(
    *,
    waveforms: list[dict],
    baseline_mode: str,
    max_plot_points: int,
    ring_start_us: float,
    ring_end_us: float,
    peak_threshold_fraction: float,
    min_peak_distance_us: float,
) -> None:
    st.subheader("Envelope")
    st.caption(
        "No modo Envelope, o gráfico mantém a onda completa no mesmo eixo, "
        "mas marca somente os máximos dominantes. Clique nos círculos para selecionar os picos usados na envoltória."
    )

    st.markdown("**1) Arquivos e janela de análise**")
    envelope_filter = st.selectbox(
        "Tipo de sinal para Envelope",
        ["Todos", "Tensão", "Corrente", "Não classificado"],
        key="envelope_role_filter_v040",
        help="Use este filtro para estudar o decaimento separadamente em tensão ou corrente, sem misturar canais por engano.",
    )
    envelope_role_map = {
        "Todos": None,
        "Tensão": "voltage",
        "Corrente": "current",
        "Não classificado": "unknown",
    }
    file_names = names_for_role(waveforms, envelope_role_map[envelope_filter])
    default_files = list(st.session_state.get("envelope_files_v0315", file_names))
    default_files = [name for name in default_files if name in file_names]
    if not default_files:
        default_files = file_names
    st.session_state["envelope_files_v0315"] = default_files
    env_selected_names = st.multiselect(
        "Arquivos no mesmo eixo",
        file_names,
        default=default_files,
        key="envelope_files_v0315",
        format_func=lambda name: _format_signal_label(name, waveforms),
        help="Selecione um ou mais arquivos. A opção 'Select all' agora mantém todos os arquivos carregados no Envelope.",
    )
    if len(env_selected_names) > 6:
        st.info(
            "Muitos arquivos no mesmo eixo podem reduzir a velocidade do clique no Envelope. "
            "A seleção é permitida, mas para análise fina recomenda-se revisar as curvas em grupos quando necessário."
        )

    control_cols = st.columns([1, 1, 1, 1])
    env_start_us = control_cols[0].number_input(
        "Início (µs)",
        value=ring_start_us,
        step=1.0,
        format="%.3f",
        key="envelope_start_us_v039",
    )
    env_end_us = control_cols[1].number_input(
        "Fim (µs)",
        value=ring_end_us,
        step=1.0,
        format="%.3f",
        key="envelope_end_us_v039",
    )
    env_threshold = control_cols[2].slider(
        "Limiar dos picos (%)",
        min_value=1,
        max_value=50,
        value=int(round(peak_threshold_fraction * 100)),
        step=1,
        key="envelope_threshold_v039",
    ) / 100.0
    env_min_distance = control_cols[3].number_input(
        "Distância mínima (µs)",
        min_value=0.001,
        value=min_peak_distance_us,
        step=0.5,
        format="%.3f",
        key="envelope_min_distance_v039",
    )
    polarity = "Somente máximos"

    auto_cols = st.columns([1, 1, 1, 1, 2])
    auto_select_enabled = auto_cols[0].checkbox(
        "Auto-selecionar",
        value=True,
        key="envelope_auto_enabled_v039",
        help="Quando ativo, o app já seleciona os picos da ressonância natural para calcular a envoltória.",
    )
    auto_n = auto_cols[1].number_input(
        "Picos por curva",
        min_value=1,
        max_value=12,
        value=3,
        step=1,
        key="envelope_auto_n_v040",
        help="Quantidade de cristas finais usadas no ajuste. O padrão é 3 picos finais do sinal.",
    )
    auto_mode = auto_cols[2].selectbox(
        "Critério",
        ["Últimos N picos", "N picos após maior pico", "N maiores picos"],
        index=0,
        key="envelope_auto_mode_v040",
        help=(
            "Últimos N picos é o padrão para a envoltória dos 3 picos finais do sinal. "
            "N picos após maior pico tenta iniciar a resposta natural após a crista dominante; "
            "N maiores picos prioriza amplitude."
        ),
    )
    focus_y = auto_cols[3].checkbox(
        "Focar Y",
        value=False,
        key="envelope_focus_y_v039",
        help="Quando ativo, aproxima a escala vertical dos picos marcados. Desative para ver toda a onda na janela.",
    )
    auto_cols[4].info(
        "O gráfico mostra a onda completa. O app marca máximos dominantes e, por padrão, "
        "seleciona os 3 picos finais do sinal para a envoltória em vermelho; a linha passa pelos máximos selecionados."
    )

    option_cols = st.columns([1, 1, 4])
    log_y_fit = option_cols[0].checkbox(
        "Envelope em log",
        value=False,
        key="envelope_log_y_v039",
    )
    normalize_env = option_cols[1].checkbox(
        "Comparar normalizado",
        value=True,
        key="envelope_compare_norm_v039",
    )
    option_cols[2].caption(
        "Use o clique no pico para desmarcar/remarcar. Se alterar N, janela, limiar ou critério, "
        "a seleção automática é recalculada."
    )

    if not env_selected_names:
        st.warning("Selecione pelo menos um arquivo para analisar o envelope.")
    else:
        selected_items = [item for item in waveforms if item["name"] in env_selected_names]
        st.markdown("**2) Seleção dos picos no mesmo eixo**")

        peaks_by_file: dict[str, pd.DataFrame] = {}
        raw_peak_count_by_file: dict[str, int] = {}
        selected_by_file: dict[str, list[int]] = {}
        peak_summary_rows = []
        detection_diagnostic_rows = []

        # Keep a compact pool of dominant maxima. This keeps the
        # image selector fast and prevents dozens of tiny late oscillations
        # from cluttering the Envelope workflow. The auto-selected N peaks
        # are chosen from this same candidate pool.
        # Keep enough candidates to make "Últimos N picos" robust, even
        # when many waveforms are overlaid. The adaptive floor below removes
        # tiny late ripples, so a larger candidate pool does not clutter as much.
        if auto_mode == "N picos após maior pico":
            # Alternative physical workflow: keep enough post-forced crests to
            # fit the natural ringdown, but avoid very late ripple/noise.
            candidate_count = max(int(auto_n) + 8, 14)
            candidate_count = min(candidate_count, 80)
            candidate_floor_fraction = max(0.035, min(0.12, float(env_threshold) * 1.10))
            detection_threshold = max(0.01, min(float(env_threshold), float(env_threshold) * 0.85))
        elif auto_mode == "Últimos N picos":
            # Legacy mode: allow a larger pool, but candidates remain upper
            # crests only. This mode can be more sensitive to tail ripple.
            candidate_count = max(int(auto_n) * 10, int(auto_n) + 20, 32)
            candidate_count = min(candidate_count, 200)
            candidate_floor_fraction = max(0.015, min(0.06, float(env_threshold) * 0.60))
            detection_threshold = max(0.006, min(float(env_threshold), float(env_threshold) * 0.45))
        else:
            # For amplitude-priority analysis, keep a stricter pool so that
            # the selected points truly represent the dominant lobes.
            candidate_count = max(int(auto_n) * 4, int(auto_n) + 8, 16)
            candidate_count = min(candidate_count, 40)
            candidate_floor_fraction = max(0.10, min(0.30, float(env_threshold) * 3.0))
            detection_threshold = float(env_threshold)

        for ring_item in selected_items:
            peak_df, raw_count = cached_dominant_positive_peaks(
                ring_item,
                start_us=env_start_us,
                end_us=env_end_us,
                baseline_mode=baseline_mode,
                threshold=detection_threshold,
                min_distance_us=env_min_distance,
                candidate_count=candidate_count,
                candidate_floor_fraction=candidate_floor_fraction,
            )
            raw_peak_count_by_file[ring_item["name"]] = raw_count
            peaks_by_file[ring_item["name"]] = peak_df

            selected_ids = selected_peak_ids_for_file(ring_item["name"])
            valid_ids = set(peak_df["peak_id"].to_list()) if not peak_df.empty else set()
            selected_ids = [peak_id for peak_id in selected_ids if peak_id in valid_ids]

            if auto_select_enabled:
                signature = _auto_selection_signature(
                    ring_item["name"],
                    peak_df,
                    int(auto_n),
                    auto_mode,
                    float(env_start_us),
                    float(env_end_us),
                    float(env_threshold),
                    float(env_min_distance),
                )
                signature_key = _auto_selection_signature_key(ring_item["name"])
                if st.session_state.get(signature_key) != signature:
                    selected_ids = auto_select_positive_peak_ids(peak_df, auto_mode, int(auto_n))
                    st.session_state[signature_key] = signature

            set_selected_peak_ids_for_file(ring_item["name"], selected_ids)
            selected_by_file[ring_item["name"]] = selected_ids
            peak_summary_rows.append(
                {
                    "arquivo": ring_item["name"],
                    "picos_brutos": raw_peak_count_by_file[ring_item["name"]],
                    "candidatos_crista": int(len(peak_df)),
                    "picos_selecionados": int(len(selected_ids)),
                }
            )
            detection_diagnostic_rows.append(
                per_signal_detection_diagnostic(
                    ring_item["name"],
                    peak_df,
                    selected_ids,
                    int(auto_n),
                    auto_mode,
                )
            )

        action_cols = st.columns([1, 1, 1, 3])
        if action_cols[0].button("Limpar seleção", key="clear_all_peak_selection_v039"):
            for name in env_selected_names:
                set_selected_peak_ids_for_file(name, [])
                # Preserve the current auto-signature so clearing does not
                # immediately reselect the same peaks on the rerun.
                peak_df = peaks_by_file.get(name, pd.DataFrame())
                st.session_state[_auto_selection_signature_key(name)] = _auto_selection_signature(
                    name,
                    peak_df,
                    int(auto_n),
                    auto_mode,
                    float(env_start_us),
                    float(env_end_us),
                    float(env_threshold),
                    float(env_min_distance),
                )
            st.session_state[_multi_last_click_key()] = None
            st.session_state[_multi_image_click_version_key()] = int(
                st.session_state.get(_multi_image_click_version_key(), 0)
            ) + 1
            st.rerun()

        if action_cols[1].button("Detectar Automático", key="detect_auto_peak_selection_v037"):
            for name in env_selected_names:
                peak_df = peaks_by_file.get(name, pd.DataFrame())
                selected_ids = auto_select_positive_peak_ids(peak_df, auto_mode, int(auto_n))
                set_selected_peak_ids_for_file(name, selected_ids)
                st.session_state[_auto_selection_signature_key(name)] = _auto_selection_signature(
                    name,
                    peak_df,
                    int(auto_n),
                    auto_mode,
                    float(env_start_us),
                    float(env_end_us),
                    float(env_threshold),
                    float(env_min_distance),
                )
            st.session_state[_multi_last_click_key()] = None
            st.session_state[_multi_image_click_version_key()] = int(
                st.session_state.get(_multi_image_click_version_key(), 0)
            ) + 1
            st.rerun()

        action_cols[2].caption(
            f"Total selecionado: {sum(len(v) for v in selected_by_file.values())}"
        )
        action_cols[3].dataframe(pd.DataFrame(peak_summary_rows), width="stretch", height=130)

        with st.expander("Diagnóstico da detecção por arquivo", expanded=True):
            st.caption(
                "Cada linha é calculada isoladamente a partir do respectivo arquivo. "
                "A sobreposição no gráfico acontece somente depois da detecção individual."
            )
            st.dataframe(pd.DataFrame(detection_diagnostic_rows), width="stretch", height=180)

        st.caption(
            "No gráfico do Envelope a onda completa permanece desenhada. "
            "As marcações aparecem somente nas cristas/máximos locais relevantes; vermelho indica os picos usados na envoltória."
        )

        if any(df.empty for df in peaks_by_file.values()):
            empty_names = [name for name, df in peaks_by_file.items() if df.empty]
            st.warning(
                "Sem cristas/máximos relevantes detectados em: " + ", ".join(empty_names) +
                ". Ajuste a janela, reduza o limiar ou diminua a distância mínima."
            )

        envelope_rows = []
        envelope_metrics_by_file: dict[str, dict] = {}
        envelope_fit_tables: dict[str, pd.DataFrame] = {}
        for ring_item in selected_items:
            name = ring_item["name"]
            selected_ids = selected_peak_ids_for_file(name)
            peak_df = peaks_by_file.get(name, pd.DataFrame())
            envelope_metrics, fit_df = fit_selected_envelope_only(
                peak_df,
                selected_ids,
                polarity=polarity,
                file_name=name,
            )
            envelope_fit_tables[name] = fit_df
            if np.isfinite(envelope_metrics.get("tau_us", np.nan)):
                envelope_metrics["series_color"] = ring_item.get(
                    "series_color_hex",
                    SERIES_COLORS_HEX[len(envelope_rows) % len(SERIES_COLORS_HEX)],
                )
                envelope_rows.append(envelope_metrics)
                envelope_metrics_by_file[name] = envelope_metrics

        if streamlit_image_coordinates is None:
            st.error(
                "O componente de clique por imagem não está instalado. Rode: "
                "pip install streamlit-image-coordinates"
            )
        else:
            if _multi_image_click_version_key() not in st.session_state:
                st.session_state[_multi_image_click_version_key()] = 0

            st.caption(
                "A legenda das curvas fica dentro do gráfico; vermelho indica os máximos selecionados e a envoltória passando por eles."
            )
            click_img, peak_pixels = build_multi_clickable_waveform_image(
                selected_items,
                peaks_by_file=peaks_by_file,
                selected_by_file=selected_by_file,
                start_us=env_start_us,
                end_us=env_end_us,
                baseline_mode=baseline_mode,
                max_points=min(max_plot_points, ENVELOPE_IMAGE_MAX_POINTS),
                focus_y_on_peaks=focus_y,
                image_width=1450,
                image_height=560,
                envelope_metrics_by_file=envelope_metrics_by_file,
            )
            image_state_signature = hashlib.md5(
                repr(
                    [
                        tuple(env_selected_names),
                        float(env_start_us),
                        float(env_end_us),
                        float(env_threshold),
                        float(env_min_distance),
                        bool(focus_y),
                        int(auto_n),
                        auto_mode,
                        {name: tuple(selected_by_file.get(name, [])) for name in env_selected_names},
                        {name: envelope_metrics_by_file.get(name, {}).get("tau_us") for name in env_selected_names},
                    ]
                ).encode("utf-8")
            ).hexdigest()[:10]
            click_data = streamlit_image_coordinates(
                click_img,
                width=1450,
                key=(
                    "envelope_multi_image_click_"
                    f"{st.session_state[_multi_image_click_version_key()]}_"
                    f"{image_state_signature}_v0311"
                ),
            )
            changed = toggle_multi_peak_selection_from_image_click(
                click_data,
                peak_pixels,
                peaks_by_file=peaks_by_file,
            )
            if changed:
                st.session_state[_multi_image_click_version_key()] = int(
                    st.session_state.get(_multi_image_click_version_key(), 0)
                ) + 1
                st.rerun()

        st.markdown("**3) Envoltórias calculadas**")
        st.caption(
            "Este item permanece separado como resumo/comparação numérica. "
            "Quando há seleção válida, a mesma envoltória visual também aparece como linha vermelha no gráfico do item 2, passando pelos picos selecionados. As métricas tau/R² continuam no resumo numérico."
        )

        if len(envelope_rows) == 0:
            st.info("Selecione pelo menos 2 picos máximos em um arquivo para calcular a primeira envoltória.")
        else:
            envelope_df = pd.DataFrame(envelope_rows)
            fig_cmp = plot_envelope_comparison(envelope_df, normalize=normalize_env)
            st.plotly_chart(fig_cmp, width="stretch", key="envelope_compare_chart_v035")
            st.dataframe(compact_metrics_table(envelope_rows), width="stretch")
            st.download_button(
                "Baixar comparação de envelopes em CSV",
                data=envelope_df.to_csv(index=False).encode("utf-8"),
                file_name="comparacao_envelopes_exponenciais.csv",
                mime="text/csv",
                key="download_envelope_compare_v035",
            )

        with st.expander("Detalhar picos selecionados e detectados", expanded=False):
            for ring_item in selected_items:
                name = ring_item["name"]
                st.markdown(f"**{name}**")
                fit_df = envelope_fit_tables.get(name, pd.DataFrame())
                peak_df = peaks_by_file.get(name, pd.DataFrame())
                if fit_df.empty:
                    st.caption("Ainda sem picos suficientes selecionados para ajuste.")
                else:
                    st.dataframe(
                        fit_df[[c for c in ["tempo_us", "tipo", "amplitude", "abs_amplitude", "envelope_amplitude", "fit_amplitude", "fit_amplitude_source", "detector_role"] if c in fit_df.columns]],
                        width="stretch",
                        height=160,
                    )
                st.dataframe(peak_df, width="stretch", height=180)
