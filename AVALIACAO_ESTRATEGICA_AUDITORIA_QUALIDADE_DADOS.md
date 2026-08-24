# Avaliação estratégica de abordagens para auditoria da qualidade de dados

## 1. Resumo executivo

O objetivo estratégico da PoC não deve ser selecionar uma ferramenta única nem produzir uma nota genérica de qualidade. Deve ser comprovar quais mecanismos conseguem detectar, explicar e priorizar diferentes problemas de dados com nível aceitável de confiança, custo e esforço operacional.

A recomendação é adotar uma **arquitetura híbrida e modular**, formada por quatro camadas complementares:

1. **Controles determinísticos**, para completude, tipos, formatos, domínios, intervalos, relações entre campos e duplicatas exatas.
2. **Perfilamento e controles estatísticos**, para valores atípicos, alterações de distribuição e mudanças de frequência.
3. **Controles semânticos e de resolução de entidades**, para categorias equivalentes, categorias inesperadas e duplicatas aproximadas.
4. **Validação referencial**, quando houver fonte externa confiável, para medir acurácia ou veracidade diretamente.

Essa combinação atende à distinção central do documento: algumas verificações são objetivas; outras dependem de histórico; e acurácia real só pode ser afirmada quando existe referência externa ou conhecimento de domínio suficiente. Na ausência dessa referência, o auditor deve apresentar **indícios de confiabilidade**, nunca afirmar que o dado é verdadeiro.

### Diretriz recomendada

Construir o auditor como uma plataforma de evidências, na qual cada achado informe:

- dimensão de qualidade afetada;
- regra, técnica ou modelo utilizado;
- campo, registro ou conjunto impactado;
- severidade e confiança do achado;
- evidência observada e baseline de comparação;
- ação recomendada;
- limitações da conclusão.

O resultado da PoC será considerado bem-sucedido se permitir decidir, por dimensão e tipo de dado, quais técnicas devem compor a primeira versão do auditor e em que condições elas são confiáveis.

## 2. Escopo e princípios de decisão

Esta avaliação deriva dos requisitos apresentados no PDF *Avaliação de abordagens para auditoria da qualidade de dados* e considera os limites atuais definidos em `deep_research/config.py`.

### Princípios

1. **Qualidade é multidimensional.** Completude, validade, consistência, unicidade, estabilidade e acurácia não são intercambiáveis.
2. **Ausência de evidência não é evidência de qualidade.** Um valor válido e estatisticamente comum ainda pode estar incorreto.
3. **Anomalia não é sinônimo de erro.** O auditor sinaliza e contextualiza; o domínio confirma.
4. **Contexto de uso define criticidade.** Um campo opcional pode ser irrelevante para um processo e essencial para outro.
5. **Explicabilidade é requisito operacional.** Um alerta sem evidência e sem indicação de causa tende a gerar fadiga e abandono.
6. **A comparação deve ocorrer por capacidade.** Ferramentas são componentes possíveis; a unidade real de avaliação é o mecanismo de detecção.
7. **O baseline deve ser versionado.** Regras, perfis, limiares e referências externas precisam ter origem e período de validade conhecidos.
8. **Não deve existir uma nota única obrigatória.** Painéis podem agregar resultados, mas precisam preservar dimensão, cobertura, confiança e severidade.

## 3. Capacidades necessárias

| Dimensão/capacidade | Questão respondida | Dependência principal | Resultado adequado |
|---|---|---|---|
| Completude | A informação necessária para o uso está presente? | Regras de obrigatoriedade por contexto | Taxa de ausência e registros afetados |
| Validade | O valor respeita tipo, formato, domínio e intervalo? | Contrato/esquema ou regra de domínio | Violações objetivas por regra |
| Consistência | Valores relacionados não se contradizem? | Regras entre campos, registros ou fontes | Contradições e regra violada |
| Unicidade | Há registros repetidos ou entidades duplicadas? | Chaves e critérios de similaridade | Pares/grupos candidatos e confiança |
| Atipicidade | O valor se afasta do comportamento esperado? | Distribuição ou vizinhança de referência | Anomalia, escore e contexto |
| Estabilidade temporal | O comportamento mudou de modo relevante? | Histórico comparável e janela temporal | Drift, magnitude e período afetado |
| Qualidade categórica | Surgiram categorias novas, raras ou equivalentes? | Vocabulário, frequências e semântica | Categoria afetada e tipo de desvio |
| Acurácia/veracidade | O valor corresponde ao estado real? | Fonte de verdade ou validação de domínio | Divergência comprovada ou indício limitado |

## 4. Avaliação estratégica das abordagens

Escala: **1 = baixa adequação** e **5 = alta adequação**. As notas servem para comparar características das abordagens e não constituem uma nota final de qualidade dos dados.

| Abordagem | Cobertura | Precisão potencial | Explicabilidade | Esforço de domínio | Adaptação a mudanças | Prioridade na PoC |
|---|---:|---:|---:|---:|---:|---|
| Regras determinísticas e contratos | 3 | 5 | 5 | 4 | 2 | Muito alta |
| Perfilamento estatístico | 4 | 3 | 4 | 2 | 3 | Muito alta |
| Detecção de drift temporal | 3 | 4 | 4 | 3 | 5 | Alta |
| Detecção de anomalias multivariadas | 4 | 3 | 2 | 3 | 4 | Média/alta |
| Validação semântica de categorias | 3 | 3 | 3 | 4 | 4 | Média |
| Resolução de entidades/duplicidade aproximada | 2 | 4 | 3 | 4 | 3 | Alta quando aplicável |
| Comparação com fonte externa | 2 | 5 | 5 | 5 | 3 | Alta quando disponível |

### 4.1 Regras determinísticas e contratos de dados

**Uso:** tipos, formatos, campos obrigatórios, domínios permitidos, intervalos, chaves, relações condicionais e consistência entre campos.

**Valor estratégico:** deve formar a base do auditor porque oferece resultados reproduzíveis, explicáveis e de baixa ambiguidade. É a melhor primeira resposta para falhas conhecidas.

**Limites:** exige conhecimento explícito; não descobre facilmente problemas novos; regras rígidas podem gerar falsos positivos quando o processo muda.

**Decisão:** incluir obrigatoriamente no MVP, com versionamento, responsável, severidade, vigência e justificativa de cada regra.

### 4.2 Perfilamento e testes estatísticos

**Uso:** distribuição, cardinalidade, percentis, frequências, dispersão, ausência, valores raros e alterações agregadas.

**Valor estratégico:** amplia a cobertura sem exigir uma regra individual para cada comportamento. É especialmente útil para estabelecer baselines e observar mudanças.

**Limites:** sensível à escolha de janelas, sazonalidade, tamanho da amostra e segmentação; uma população heterogênea pode produzir alertas enganosos.

**Decisão:** incluir no MVP com segmentação por contexto, histórico versionado e limiares calibrados empiricamente.

### 4.3 Detecção de drift

**Uso:** mudanças em distribuições numéricas, frequência de categorias, taxa de nulos, cardinalidade e relações entre variáveis.

**Valor estratégico:** detecta degradações silenciosas e mudanças de processo que regras estáticas não percebem.

**Limites:** drift pode refletir mudança legítima do negócio. A abordagem depende de um período de referência representativo e de tratamento explícito da sazonalidade.

**Decisão:** testar na PoC com mudanças graduais e abruptas, baselines móveis e fixos, e alertas que indiquem magnitude — sem classificar automaticamente o dado como errado.

### 4.4 Detecção de anomalias

**Uso:** valores atípicos univariados e combinações incomuns de atributos.

**Valor estratégico:** encontra casos não antecipados e relações que seriam custosas de codificar manualmente.

**Limites:** modelos podem ser pouco explicáveis, instáveis em amostras pequenas e propensos a confundir eventos raros legítimos com erros.

**Decisão:** comparar primeiro métodos simples e interpretáveis com métodos multivariados. Só adotar maior complexidade se houver ganho mensurável em detecção e falso positivo.

### 4.5 Validação categórica e semântica

**Uso:** categorias desconhecidas, variações ortográficas, sinônimos, mudanças de frequência e valores textualmente válidos, mas semanticamente inadequados.

**Valor estratégico:** cobre problemas invisíveis para validações de tipo e formato.

**Limites:** requer vocabulário controlado, exemplos ou conhecimento de domínio; similaridade textual não comprova equivalência semântica.

**Decisão:** combinar lista de valores autorizados, normalização e similaridade como geradora de candidatos. Alterações automáticas devem exigir alta confiança ou aprovação humana.

### 4.6 Duplicidade exata e resolução de entidades

**Uso:** cópias exatas e registros que representam a mesma entidade com pequenas diferenças.

**Valor estratégico:** a duplicidade exata tem baixo custo e alto retorno; a aproximada pode ser essencial para cadastros, clientes, fornecedores e ativos.

**Limites:** critérios frouxos mesclam entidades diferentes; critérios rígidos deixam passar duplicatas. O custo cresce com o volume e a quantidade de comparações.

**Decisão:** separar duas capacidades: deduplicação exata no núcleo básico e resolução aproximada como módulo especializado, com bloqueio de candidatos, escore e revisão dos casos limítrofes.

### 4.7 Comparação entre fontes e referência externa

**Uso:** validação direta contra cadastro mestre, sistema de origem ou fonte reconhecida.

**Valor estratégico:** é o mecanismo mais forte para acurácia e veracidade.

**Limites:** a referência pode estar desatualizada, possuir qualidade inferior ou usar chaves incompatíveis. Sua governança é parte da solução.

**Decisão:** quando disponível, registrar proveniência, data, cobertura e confiabilidade da referência. Sem isso, apresentar apenas concordância entre fontes, não “verdade”.

## 5. Estratégia recomendada para a PoC

### 5.1 Hipóteses a validar

- Regras determinísticas detectam falhas conhecidas com alta precisão e explicabilidade.
- Perfilamento e drift detectam mudanças coletivas que não aparecem em registros isolados.
- Métodos simples de anomalia são suficientes para parte relevante dos valores atípicos.
- Técnicas multivariadas agregam valor apenas em cenários específicos e com custo operacional maior.
- Normalização e similaridade melhoram a detecção de categorias equivalentes e duplicatas aproximadas.
- Uma combinação de mecanismos oferece maior cobertura que qualquer componente isolado.

### 5.2 Desenho experimental

1. Selecionar um conjunto real conhecido, com autorização de uso e dados sensíveis protegidos.
2. Produzir uma cópia de referência e documentar seus problemas já conhecidos.
3. Separar dados de calibração, baseline histórico e avaliação; os dados de avaliação não devem ser usados para ajustar limiares.
4. Injetar falhas controladas com identificador, dimensão, campo, severidade, quantidade e método de alteração.
5. Executar cada abordagem isoladamente e, depois, a composição recomendada.
6. Comparar achados com o catálogo de falhas injetadas e com problemas reais confirmados.
7. Submeter casos ambíguos a especialistas de domínio e registrar a decisão.
8. Repetir o teste em diferentes volumes, segmentos e períodos.

### 5.3 Cenários mínimos de teste

| Cenário | Exemplos de injeção | Variação necessária |
|---|---|---|
| Ausência | nulo, vazio, campo omitido | Campo crítico e opcional |
| Invalidade | tipo, formato, intervalo, domínio | Erro óbvio e limítrofe |
| Inconsistência | datas invertidas, totais incompatíveis | Dentro e entre registros |
| Categoria | nova grafia, sinônimo, categoria inédita | Rara, frequente e gradual |
| Outlier | extremo isolado, combinação improvável | Univariado e multivariado |
| Drift numérico | mudança de média, variância ou forma | Abrupto, gradual e sazonal |
| Drift categórico | mudança de frequência, surgimento/sumiço | Global e por segmento |
| Duplicidade | cópia exata e pequenas alterações | Diferentes níveis de similaridade |
| Fonte externa | valor divergente ou referência desatualizada | Com e sem chave confiável |

As injeções devem ocorrer em níveis progressivos de intensidade. Isso permite medir não apenas se uma técnica detecta o problema, mas a partir de que magnitude ela se torna confiável.

### 5.4 Métricas de avaliação

Para cada abordagem, dimensão, tipo de dado e intensidade da falha:

- **recall/sensibilidade:** proporção das falhas conhecidas detectadas;
- **precisão:** proporção dos alertas que correspondem a falhas;
- **taxa de falso positivo:** dados corretos classificados como problemáticos;
- **F1:** síntese útil quando precisão e recall têm importância semelhante;
- **cobertura:** campos, tipos e dimensões suportados;
- **tempo até detecção:** relevante para auditoria contínua;
- **custo computacional:** tempo, memória e comportamento por volume;
- **esforço de configuração e manutenção:** regras, baselines e retreinamento;
- **explicabilidade e acionabilidade:** capacidade de justificar e corrigir o achado;
- **estabilidade:** variação dos resultados em execuções, amostras e períodos diferentes.

Os resultados devem ser apresentados em uma matriz por cenário. Uma média global pode esconder que uma abordagem excelente para validade é inútil para drift.

### 5.5 Critérios de aprovação

Os limiares numéricos devem ser definidos segundo criticidade e custo do erro. Como regra de governança:

- controles bloqueantes exigem alta precisão e regra objetiva;
- alertas de investigação podem aceitar menor precisão, desde que ordenados por risco;
- métodos que não expliquem minimamente a evidência não devem gerar bloqueio automático;
- ganhos pequenos de detecção não justificam complexidade operacional desproporcional;
- toda capacidade aprovada precisa ter responsável, rotina de calibração e procedimento de exceção.

## 6. Arquitetura inicial do auditor

```text
Fontes de dados
      |
      v
Ingestão + metadados + contrato
      |
      +--> Regras determinísticas
      +--> Perfil estatístico e baseline histórico
      +--> Anomalias e drift
      +--> Categorias e resolução de entidades
      +--> Comparação com referências externas
                    |
                    v
        Normalização de evidências
                    |
                    v
      Priorização por impacto e confiança
                    |
                    v
 Relatório/API + histórico + revisão humana
```

### Contrato mínimo de um achado

```json
{
  "dimension": "validade",
  "scope": "campo_ou_conjunto",
  "check_id": "identificador_versionado",
  "severity": "alta",
  "confidence": 0.98,
  "observed": "evidencia_resumida",
  "expected": "regra_ou_baseline",
  "reference_period": "periodo_se_aplicavel",
  "affected_count": 12,
  "recommendation": "acao_sugerida",
  "limitations": "limites_da_conclusao"
}
```

A confiança mede a força da evidência do mecanismo, enquanto a severidade representa impacto de negócio. Esses conceitos não devem ser combinados em um único campo.

## 7. Estratégia de ferramentas

A seleção de software deve ocorrer depois de definir as capacidades e executar testes comparáveis. A recomendação não é instalar todas as opções: cada grupo abaixo contém uma escolha principal e alternativas para contextos específicos.

### 7.1 Stack recomendada para a PoC

| Capacidade | Ferramenta principal | Papel na PoC | Licença do núcleo | Decisão sugerida |
|---|---|---|---|---|
| Contrato e validação de DataFrames | [Pandera](https://pandera.readthedocs.io/en/stable/) | Tipos, nulos, intervalos, domínios, regras entre colunas e validação na entrada da API | MIT | **Adotar no primeiro experimento** |
| Suítes de qualidade e evidências | [GX Core](https://docs.greatexpectations.io/docs/core/introduction/gx_overview/) | Expectations versionadas, validações, checkpoints e documentação dos resultados | Apache-2.0 | **Avaliar como motor central** |
| Perfilamento, qualidade e drift | [Evidently](https://docs.evidentlyai.com/docs/library/overview) | Comparação entre referência e período atual, testes de drift e relatórios | Apache-2.0 | **Adotar para drift em lote** |
| Anomalias tabulares | [scikit-learn](https://scikit-learn.org/stable/modules/outlier_detection.html) e [PyOD](https://github.com/yzhao062/pyod) | Baselines interpretáveis e comparação de detectores | BSD-3-Clause e BSD-2-Clause | **Testar em modo sinalizador** |
| Duplicidade aproximada | [Splink](https://moj-analytical-services.github.io/splink/) | Linkagem probabilística, bloqueio de candidatos, escores e agrupamento | MIT | **Adotar se houver entidades multicoluna** |
| Normalização categórica/textual | [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | Distâncias e similaridade para gerar candidatos de grafias equivalentes | MIT | **Adotar como componente auxiliar** |
| Execução analítica local | [DuckDB](https://duckdb.org/why_duckdb) | Consultas sobre CSV/Parquet, agregações e backend local do Splink | MIT | **Adotar na PoC local** |

#### Composição mínima recomendada

1. **Pandera** na fronteira de ingestão para contrato estrutural e falhas objetivas.
2. **GX Core** como candidato a motor de regras, histórico de validações e evidências padronizadas.
3. **Evidently** para comparar baseline e lote corrente e medir drift.
4. **scikit-learn** como baseline de anomalias; incluir **PyOD** somente para comparar métodos adicionais sob o protocolo da PoC.
5. **RapidFuzz** para normalização e **Splink** apenas nos conjuntos que realmente demandem resolução de entidades.
6. **DuckDB** para acelerar perfilamento, agregações e experimentos locais sem introduzir um servidor adicional.

Pandera e GX Core têm alguma sobreposição, mas papéis diferentes nesta proposta: Pandera protege DataFrames e contratos próximos ao código; GX Core organiza suítes, execuções e resultados de auditoria. A PoC deve medir se essa separação compensa a duplicidade. Se o custo operacional for alto, manter somente GX Core ou somente Pandera mais o contrato comum de achados.

### 7.2 Alternativas por contexto

| Contexto | Alternativa | Quando preferir | Principal ressalva |
|---|---|---|---|
| Regras declarativas em SQL/YAML | [Soda Core](https://docs.soda.io/) | Equipe orientada a SQL, contratos YAML e múltiplas fontes de dados | Separar recursos do Core aberto das extensões e serviços comerciais; validar licença e TCO da versão escolhida |
| Grandes volumes já processados em Spark | [Deequ](https://github.com/awslabs/deequ) | A organização já opera Apache Spark e precisa executar verificações distribuídas | Introduz stack Scala/Spark, excessiva para a PoC Python local |
| Drift evento a evento/streaming | [River](https://github.com/online-ml/river) | O requisito for detecção incremental, sem reprocessar todo o histórico | Complexidade maior; o próprio projeto recomenda batch quando online não é necessário |
| Pipelines SQL existentes em dbt | [dbt data tests](https://docs.getdbt.com/docs/build/data-tests) | O dado auditado já é modelado e implantado por dbt | Cobertura focada no warehouse e nas relações modeladas; não substitui anomalia, drift ou resolução de entidades |
| Plataforma gerenciada | GX Cloud, Soda Cloud ou serviço equivalente | Houver necessidade comprovada de UI compartilhada, alertas, governança e suporte | Custo recorrente, envio de metadados/dados, dependência do fornecedor e diferenças frente ao núcleo aberto |

Essas alternativas não devem ser comparadas em uma única disputa. Deequ responde a escala Spark; River, a streaming; dbt, à validação dentro de pipelines SQL; e plataformas gerenciadas, à operação colaborativa. A decisão depende da arquitetura produtiva pretendida.

### 7.3 Cobertura funcional esperada

| Ferramenta | Completude/validade | Consistência | Perfil/drift | Anomalias | Categorias | Duplicidade aproximada | Evidência/relatório |
|---|---:|---:|---:|---:|---:|---:|---:|
| Pandera | Alta | Alta no DataFrame | Baixa | Baixa | Média | Não | Média |
| GX Core | Alta | Alta, inclusive SQL customizado | Média | Baixa/média | Média | Não | Alta |
| Evidently | Média | Baixa | Alta | Média | Alta para mudanças de frequência | Não | Alta |
| scikit-learn/PyOD | Não | Multivariada, indireta | Baixa | Alta | Baixa | Não | Baixa |
| RapidFuzz | Não | Não | Não | Não | Alta para similaridade textual | Média, por campo | Baixa |
| Splink | Não | Não | Não | Não | Média | Alta | Alta para escores de ligação |
| Soda Core | Alta | Alta | Depende da edição/recurso | Depende da edição/recurso | Média | Não | Alta |
| Deequ | Alta | Alta | Média | Média | Média | Não | Média |

“Alta” significa boa adequação à capacidade, não desempenho garantido. A PoC deve confirmar cobertura, falsos positivos, desempenho e facilidade de integração com o contrato de achados.

### 7.4 Critérios de seleção e descarte

Para cada alternativa, registrar:

- capacidades cobertas e tipos de dados aceitos;
- extensibilidade para regras e conectores próprios;
- execução em lote, streaming ou ambos;
- explicabilidade e formato dos resultados;
- integração, observabilidade e operação;
- desempenho no volume esperado;
- maturidade e risco de dependência do fornecedor;
- licença, restrições de redistribuição e compatibilidade jurídica;
- custos de assinatura, infraestrutura, volume, suporte e manutenção interna.

Uma biblioteca especializada pode ser melhor que uma plataforma ampla em determinada capacidade. A arquitetura deve permitir substituição de componentes e manter um contrato de achados independente da ferramenta.

#### Gates de decisão

- **GX Core versus Soda Core:** levar apenas um deles à arquitetura produtiva, salvo justificativa clara de capacidades não sobrepostas.
- **Pandera mais motor central:** manter Pandera se reduzir falhas na ingestão e simplificar contratos de código sem duplicar manutenção de regras.
- **PyOD:** aprovar somente se superar os baselines do scikit-learn em cenários relevantes, com estabilidade e explicação aceitáveis.
- **Splink:** aprovar somente com dataset rotulado ou amostra revisada que permita calibrar limiar e medir falso pareamento.
- **River:** adiar enquanto auditoria em lote atender ao tempo de detecção exigido.
- **Plataforma comercial:** avaliar somente após a PoC comprovar necessidade de recursos operacionais que o núcleo aberto não cobre.

### 7.5 Compatibilidade com o projeto atual

O interpretador padrão do shell usa **Python 3.14.0** e não possui FastAPI instalado. O ambiente Conda utilizado pelo projeto usa **Python 3.13.9**, FastAPI 0.140.9 e Pydantic 2.12.3; foi nesse ambiente que o endpoint de auditoria foi validado. Em agosto de 2026, a documentação do GX Core declara suporte a Python 3.10–3.13, enquanto o Soda Core v4 declara suporte oficial até Python 3.12. Caso essas ferramentas sejam adicionadas, a PoC deve usar **ambiente isolado em Python 3.12**, sem alterar inicialmente o ambiente da API.

Nenhuma das ferramentas recomendadas, exceto scikit-learn, está instalada no ambiente atual. Portanto, a inclusão em `requirements-api.txt` deve ocorrer somente após um *spike* de compatibilidade e congelamento de versões. Bibliotecas de auditoria podem também ser mantidas em um arquivo de dependências próprio, reduzindo acoplamento com a API e com o pipeline de pesquisa documental.

Licenças, preços e condições comerciais mudam. As licenças da tabela foram verificadas nas fontes oficiais em 18 de agosto de 2026, mas a validação jurídica deve considerar a versão exata, dependências transitivas, forma de distribuição e serviços comerciais eventualmente conectados.

## 8. Impacto da configuração atual da pesquisa

O arquivo `deep_research/config.py` estabelece:

- até **3 rodadas de pesquisa**;
- até **4 subquestões**;
- **10 candidatos** de recuperação e até **10 resultados** após reranqueamento;
- fragmentos de até **512 tokens** no processamento de documentos;
- arquivo máximo de **20 MB**.

Para o PDF analisado, com quatro páginas e cerca de 68 KB, os limites de tamanho são suficientes. Entretanto, a avaliação bibliográfica completa proposta pelo documento é ampla. Quatro subquestões devem ser reservadas para eixos estratégicos, por exemplo:

1. métodos objetivos: completude, validade e consistência;
2. anomalias, drift e qualidade categórica;
3. duplicidade, comparação entre fontes e acurácia;
4. ferramentas, licenças, custos e arquitetura de integração.

O limite de 512 tokens por fragmento favorece recuperação pontual, mas pode separar premissas, método e limitações de um mesmo estudo. Para a etapa bibliográfica, recomenda-se preservar metadados de seção/página e usar sobreposição entre fragmentos. A recuperação de apenas 10 trechos por consulta deve ser validada contra um conjunto de perguntas conhecido; se fontes relevantes ficarem de fora, o ajuste deve ocorrer antes de usar o sistema para decisões de ferramenta.

As credenciais e modelos definidos por variáveis de ambiente também afetam reprodutibilidade. A PoC deve registrar versão do modelo, parâmetros, data da execução e fontes recuperadas.

## 9. Roadmap proposto

### Fase 1 — Fundação e baseline

- definir dimensões, glossário, casos de uso e campos críticos;
- selecionar dataset e criar catálogo de falhas;
- implementar contrato comum de achados;
- estabelecer métricas, baseline e protocolo de injeção.

**Saída:** plano experimental reproduzível e dataset de referência.

### Fase 2 — Núcleo objetivo

- testar completude contextual, validade, consistência e duplicidade exata;
- medir desempenho, cobertura, falso positivo e esforço de manutenção;
- documentar exceções e responsabilidades.

**Saída:** núcleo determinístico candidato ao MVP.

### Fase 3 — Comportamento e semântica

- testar outliers, drift numérico e categórico;
- avaliar categorias equivalentes e duplicidade aproximada;
- comparar técnicas simples e complexas sob o mesmo protocolo.

**Saída:** módulos adicionais aprovados por evidência.

### Fase 4 — Referências, composição e decisão

- integrar fontes externas onde existirem;
- executar a composição completa;
- avaliar custo total, licenças e alternativas de implementação;
- definir o backlog e a arquitetura da primeira versão produtiva.

**Saída:** decisão arquitetural, matriz de capacidades e plano de implantação.

## 10. Riscos e controles

| Risco | Consequência | Controle recomendado |
|---|---|---|
| Dataset pouco representativo | Conclusões que não generalizam | Incluir períodos, segmentos e volumes distintos |
| Falhas artificiais simplistas | Superestimação da capacidade | Combinar injeções e incidentes reais confirmados |
| Baseline contaminado | Normalização de dados ruins | Curadoria, versionamento e aprovação do baseline |
| Excesso de alertas | Fadiga operacional | Calibração por risco, deduplicação e priorização |
| Confundir anomalia com erro | Correções indevidas | Linguagem de evidência e revisão humana |
| Confundir validade com veracidade | Falsa confiança | Rotular claramente o tipo e limite da verificação |
| Regras sem governança | Obsolescência e conflitos | Proprietário, versão, vigência e procedimento de exceção |
| Modelo opaco | Baixa confiança e difícil correção | Evidência, explicações locais e fallback interpretável |
| Dependência de fornecedor | Custo ou bloqueio tecnológico | Contrato comum e componentes substituíveis |
| Licença/custo incompatível | Impedimento de adoção | Validação jurídica e TCO antes da decisão final |

## 11. Entregáveis esperados

Ao final da PoC, devem existir:

1. taxonomia de dimensões e tipos de problema;
2. dataset de referência e catálogo reproduzível de falhas;
3. matriz abordagem × dimensão × tipo de dado;
4. resultados de precisão, recall, falso positivo, desempenho e esforço;
5. registro das limitações e condições de uso de cada técnica;
6. inventário de ferramentas, componentes, licenças e custos verificados;
7. arquitetura inicial e contrato comum de achados;
8. backlog priorizado para o MVP;
9. processo de revisão humana, exceção e recalibração;
10. relatório de decisão que preserve as evidências, sem depender de uma nota única.

## 12. Conclusão

A estratégia com melhor relação entre cobertura, confiança e viabilidade é começar por controles determinísticos e perfilamento, acrescentar drift, anomalias e técnicas semânticas apenas onde os testes demonstrem ganho, e tratar comparação com fonte externa como uma capacidade distinta de verificação de acurácia.

O diferencial do auditor não será a quantidade de testes disponíveis, mas sua capacidade de produzir evidências rastreáveis, distinguir erro comprovado de suspeita, adaptar-se ao contexto de uso e manter resultados acionáveis ao longo do tempo.

## 13. Implementação automática disponível

A análise está integrada ao fluxo principal: todo CSV enviado para `POST /documents` é auditado automaticamente antes da indexação, e o relatório é retornado no campo `data_quality` junto com o `document_id`. PDFs seguem o fluxo documental sem auditoria tabular e retornam `data_quality: null`.

O motor de validade utiliza [Pandera](https://pandera.readthedocs.io/en/stable/) em modo `lazy`, permitindo coletar todas as incompatibilidades de formato antes de produzir os achados. Na dimensão de consistência, o Pandera também valida relações entre pares de datas e limites numéricos, enquanto o Pandas agrupa atributos por entidade e reconcilia valores entre o CSV atual e a referência. O [scikit-learn](https://scikit-learn.org/stable/modules/outlier_detection.html) executa `IsolationForest` para sinalizar combinações numéricas incomuns; o [RapidFuzz](https://rapidfuzz.github.io/RapidFuzz/) compara grafias de categorias; e o [Splink](https://moj-analytical-services.github.io/splink/) gera candidatos a duplicatas aproximadas por bloqueio exato e similaridade Jaro-Winkler. Quando existe CSV de referência, o [Evidently](https://docs.evidentlyai.com/metrics/preset_data_drift) executa `DataDriftPreset` sobre colunas numéricas e categóricas elegíveis. O motor nativo permanece responsável pelo parsing, inferência semântica de colunas, completude, IQR, duplicidade exata, mudanças de esquema e variação na taxa de ausência.

A API também mantém o endpoint independente `POST /data-quality/analyze`, que recebe um CSV atual e, opcionalmente, um CSV histórico de referência. Essa segunda rota é útil para comparar períodos sem indexar o arquivo. Ambas as execuções são determinísticas e não dependem de LLM.

### Arquitetura modular por dimensão

`deep_research/services/data_quality_service.py` preserva a função pública `analyze_csv_quality` e atua somente como orquestrador. As avaliações e a infraestrutura compartilhada ficam no pacote `deep_research/services/data_quality/`:

| Arquivo | Dimensão ou papel | Biblioteca principal | Métodos de entrada |
|---|---|---|---|
| `profiling.py` | Completude, perfil estatístico, IQR univariado e categorias raras | Python `statistics` e `Counter` | `profile_column` |
| `validity.py` | Validade estrutural e de formatos | Pandera e Pandas | `check_structural_rows`, `check_formats` |
| `consistency.py` | Consistência entre colunas, entidades e fontes | Pandera e Pandas | `check_consistency`, `check_cross_source_consistency` |
| `outliers.py` | Atipicidade multivariada | scikit-learn | `check_multivariate` |
| `categorical.py` | Similaridade entre categorias | RapidFuzz | `check_category_similarity` |
| `duplicates.py` | Duplicidade exata e aproximada | Python nativo, Splink, DuckDB, RapidFuzz e Pandas | `check_exact_duplicates`, `check_approximate_duplicates` |
| `drift.py` | Comportamento temporal | Evidently e Pandas | `check_drift` |
| `dimensions.py` | Consolidação dos estados das oito dimensões | Python nativo | `build_dimension_results` |
| `core.py` | Parsing, tipos, contexto e conversores compartilhados | Python nativo | `parse_csv` e utilitários |

### Métodos das dimensões

- `profile_column` calcula ausências, tipo predominante, cardinalidade, valores frequentes e estatísticas. Também registra outliers por IQR e categorias de ocorrência única quando há amostra suficiente.
- `check_structural_rows` detecta linhas com largura diferente do cabeçalho; `check_formats` usa validação `lazy` do Pandera para reunir todas as células incompatíveis com o tipo inferido.
- `check_consistency` executa três famílias de regras: ordem cronológica, coerência de limites numéricos e estabilidade de atributos por entidade. Os pares são inferidos apenas quando os cabeçalhos compartilham tokens semânticos completos.
- `check_cross_source_consistency` agrupa valores por chave nos dois arquivos e compara somente entidades presentes em ambos. A referência é tratada como conjunto comparável, não como fonte de verdade.
- `check_multivariate` seleciona colunas numéricas elegíveis, imputa ausências pela mediana e exige concordância de pelo menos dois entre três modelos `IsolationForest`.
- `check_category_similarity` compara categorias de baixa cardinalidade com `WRatio` e registra pares a partir de 90% de similaridade.
- `check_exact_duplicates` conta repetições integrais de linhas; `check_approximate_duplicates` usa regras de bloqueio e similaridade textual para gerar candidatos, sem consolidá-los automaticamente.
- `check_drift` detecta colunas adicionadas ou removidas, variação relevante na ausência e drift de distribuição nas colunas elegíveis.
- `build_dimension_results` converte a cobertura e as severidades dos achados nos estados `aprovada`, `atencao`, `critica` ou `nao_avaliada`.

### Entrada

No fluxo principal, basta enviar o CSV normalmente:

```bash
curl -X POST http://127.0.0.1:8000/documents \
  -F "file=@dados_atuais.csv;type=text/csv"
```

Esse fluxo executa completude, validade, consistência, atipicidade, qualidade categórica e duplicidade. Como não recebe um baseline, `comportamento_temporal` permanece como não avaliado.

Para incluir comparação temporal, use a rota especializada abaixo.

Requisição `multipart/form-data`:

- `file`: CSV atual obrigatório, limitado a 20 MB;
- `reference_file`: CSV de referência opcional, também limitado a 20 MB.

Exemplo com cURL:

```bash
curl -X POST http://127.0.0.1:8000/data-quality/analyze \
  -F "file=@dados_atuais.csv;type=text/csv" \
  -F "reference_file=@dados_referencia.csv;type=text/csv"
```

O arquivo de referência representa um período considerado comparável, e não uma fonte de verdade. Por isso, ele habilita a dimensão `comportamento_temporal`, mas não altera `acuracia_veracidade`, que permanece como não avaliada.

### Verificações implementadas

| Dimensão | Verificação automática | Evidência produzida |
|---|---|---|
| Completude | Vazios e marcadores `null`, `none`, `n/a`, `na` e `nan` | Contagem, percentual e linhas afetadas |
| Validade | Pandera: incompatibilidade com o tipo predominante; motor nativo: largura das linhas | Tipo inferido, confiança, Check executado e valores divergentes |
| Consistência | Pandera para ordem entre datas e limites numéricos; Pandas para estabilidade de atributos por entidade e comparação entre fontes | Regra, motor, colunas, entidades comparadas, percentuais e linhas contraditórias |
| Atipicidade | IQR univariado e `IsolationForest` multivariado para conjuntos com ao menos 20 linhas e duas colunas numéricas | Limites, valores, linhas, variáveis usadas e escore de anomalia |
| Qualidade categórica | Categorias raras e pares com `WRatio` do RapidFuzz a partir de 90% em campos de até 50 categorias | Categorias raras, pares semelhantes e escore textual |
| Duplicidade | Linhas idênticas e candidatos aproximados do Splink, entre 20 e 2.000 linhas, com bloqueio por campo de apoio e Jaro-Winkler a partir de 0,92 | Grupos exatos, pares candidatos, regra de bloqueio e similaridade textual |
| Comportamento temporal | Evidently para drift de distribuição; motor nativo para esquema e ausência | Método estatístico, score, limiar e evidências atuais/referência |
| Acurácia/veracidade | Não avaliada automaticamente | Explicação da necessidade de referência externa confiável |

### Saída

O relatório JSON contém:

- resumo do dataset, sem nota única de qualidade;
- situação separada das oito dimensões;
- perfil de cada coluna;
- achados ordenados por severidade;
- confiança, escopo, evidências, métricas e recomendação de cada achado;
- limitações explícitas da análise.

Os estados possíveis de uma dimensão são `aprovada`, `atencao`, `critica` e `nao_avaliada`. `Aprovada` significa apenas que os testes executados não encontraram problemas; não representa certificação de que os dados são verdadeiros.

### Próxima evolução recomendada

1. permitir contrato de domínio com obrigatoriedade, tipo, domínio e intervalo por coluna;
2. externalizar em contrato configurável as regras de consistência atualmente inferidas pelos nomes das colunas;
3. calibrar o Splink com pares rotulados para evoluir dos candidatos determinísticos à resolução probabilística;
4. persistir baselines, achados e decisões humanas;
5. calibrar limiares com o dataset de falhas controladas da PoC;
6. somente então avaliar GX Core e métodos adicionais onde a implementação básica não oferecer cobertura suficiente.

## Rastreabilidade ao documento-base

- **Página 1:** objetivo da PoC; confiabilidade para uso; completude, validade e consistência.
- **Página 2:** atipicidade; dados categóricos; comportamento temporal; duplicidade; distinção entre acurácia e indícios de confiabilidade.
- **Página 3:** investigação de métodos; papel de ferramentas; licenças e custos; injeção controlada de falhas; controle de falsos positivos; rejeição de uma nota única.
- **Página 4:** estrutura inicial do auditor; separação entre verificações objetivas, históricas e dependentes de referência externa ou domínio.
