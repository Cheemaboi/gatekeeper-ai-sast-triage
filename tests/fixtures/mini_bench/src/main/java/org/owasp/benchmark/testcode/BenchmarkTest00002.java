package org.owasp.benchmark.testcode;
public class BenchmarkTest00002 {
  public void doPost(javax.servlet.http.HttpServletRequest request) throws Exception {
    String param = request.getParameter("id");
    String bar = Helper.choose(param);
    String sql = "SELECT * FROM USERS WHERE ID='" + bar + "'";
    java.sql.Statement st = org.owasp.benchmark.helpers.DatabaseHelper.getSqlStatement();
    st.execute(sql);
  }
}
