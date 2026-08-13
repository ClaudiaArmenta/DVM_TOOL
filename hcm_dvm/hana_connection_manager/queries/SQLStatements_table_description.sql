WITH MAIN AS
(
SELECT
  cs.host,
  cs.port,
  cs.schema_name,
  'C' STORE,
  cs.table_name,
  sum(cs.RECORD_COUNT) as record_count,
  round(SUM(disk.DISK_SIZE) / 1024 / 1024 / 1024, 2) as DISK_GB,
  ( SELECT round(SUM(P.MAIN_PHYSICAL_SIZE_IN_PAGE_LOADABLE) / 1024 / 1024 / 1024, 2) FROM M_CS_COLUMNS_PERSISTENCE AS P 
    WHERE P.TABLE_NAME = CS.TABLE_NAME AND p.host = cs.host and p.port = cs.port )  NSE_GB,
  round(sum(cs.MEMORY_SIZE_IN_TOTAL + cs.PERSISTENT_MEMORY_SIZE_IN_TOTAL) / 1024 / 1024 / 1024, 2) MEM_GB,
  round(sum(cs.PERSISTENT_MEMORY_SIZE_IN_TOTAL) / 1024 / 1024 / 1024, 2) PERSISTENT_MEM_GB,
  round(sum(cs.MEMORY_SIZE_IN_PAGE_LOADABLE_MAIN) / 1024 / 1024 / 1024, 2) NSE_BUFFER_MEM_GB,
  left(( select partition_spec from tables where table_name = cs.table_name and schema_name = cs.schema_name )) as partitioning,
  count(*) as part_count
  from m_cs_tables as cs
  LEFT JOIN M_TABLE_PERSISTENCE_LOCATION_STATISTICS as disk
  on cs.table_name   = disk.table_name
  and cs.host        = disk.host
  and cs.port        = disk.port
  and cs.schema_name = disk.schema_name
  and cs.part_id     = disk.part_id
  group by cs.table_name, cs.schema_name, cs.host, cs.port 
  HAVING 
  SUM(CS.RECORD_COUNT) >= 100
UNION
( SELECT
  rs.host,
  rs.port,
  rs.SCHEMA_NAME,
  'R' STORE,
  rs.TABLE_NAME,
  SUM(rs.RECORD_COUNT) RECORD_COUNT,
  round(SUM(disk.DISK_SIZE) / 1024 / 1024 / 1024, 2) as DISK_GB,
  0 NSE_GB,
  round(SUM(rs.USED_FIXED_PART_SIZE + rs.USED_VARIABLE_PART_SIZE) / 1024 / 1024 / 1024, 2) MEM_GB,
  0 PERSISTENT_MEM_GB,
  0 NSE_BUFFER_MEM_GB,
  '' as Partitioning,
  count(*) as part_count
        FROM
          M_RS_TABLES as rs 
               LEFT JOIN 
                 M_TABLE_PERSISTENCE_LOCATION_STATISTICS as disk
               on  rs.table_name  = disk.table_name
               and rs.host        = disk.host
               and rs.port        = disk.port
               and rs.schema_name = disk.schema_name
        GROUP BY
          rs.HOST,
          rs.PORT,
          rs.SCHEMA_NAME,
          rs.TABLE_NAME
        HAVING
          SUM(rs.USED_FIXED_PART_SIZE + rs.USED_VARIABLE_PART_SIZE) >= 1024 * 1024
      )
),
LOB AS 
( SELECT
  host,
  port,
  schema_name,
  table_name,
  round(sum(DISK_SIZE) / 1024 / 1024 / 1024, 2) LOB_DISK_GB,
  round(sum(MEMORY_SIZE) / 1024 / 1024 / 1024, 2) LOB_MEM_GB
  FROM M_TABLE_LOB_STATISTICS
  group by table_name, schema_name, host, port),
TABLE_GROWTH AS
( SELECT * FROM DUMMY )
SELECT 
  top 100
  main.host,
  main.port,
  main.schema_name,
  main.store,
  main.table_name,
  main.record_count,
  main.DISK_GB,
  main.NSE_GB,
  main.MEM_GB,
  lob.LOB_DISK_GB,
  lob.LOB_MEM_GB,
  partitioning,
  part_count, 
  name.ddtext
  from main as main 
  left join lob as lob
  on main.table_name = lob.table_name
  and main.host       = lob.host
  and main.port       = lob.port
  and main.schema_name = lob.schema_name
  left join dd02t as name
  on main.table_name = name.tabname
  and name.ddlanguage = 'E'
  order by main.disk_gb desc
